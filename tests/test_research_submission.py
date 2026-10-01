from __future__ import annotations

import copy
import io
import json
import shutil
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from tests import test_multidimensional_stage as fixtures
from tests import test_multidimensional_references as references
from product.runtime.fixture_mcp import StatelessFixtureTools, serve_stdio
from product.runtime.codex_hook_recorder import (
    handle_hook_event, _research_report_monetary_findings,
)
from product.runtime.multidimensional_stage import (
    build_multidimensional_dispatch_packet, finalize_multidimensional_task_evidence,
    serialize_multidimensional_initial_context, serialize_multidimensional_model_context,
)
from product.runtime.research_submission import (
    _directory, _assemble_v3_draft, _citation_review, _source_evidence_review, MAX_CITATION_REVIEW_BYTES,
    LEGACY_VERSION, VERSION, FORMAL_VERSION, SHORT_RECEIPT_VERSION, BOUNDED_REVISION_VERSION, _assemble_v4_draft, resolve,
    selected_calculations_for_report,
)
from product.runtime.hashing import canonical_hash
from tests.historical_submission_fixture import read_historical_report_fixture, store_historical_report_fixture


class SourceEvidenceReviewTests(unittest.TestCase):
    def test_only_queried_allowed_licensed_excerpt_is_echoed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "evidence").mkdir()
            (root / "events/mcp").mkdir(parents=True)
            gate = {"allowed_evidence": [
                {"evidence_id": "ev-note", "value": {"content_tier": "LICENSED_API_CONTENT",
                    "content": "管理层将 FY2028 收入指引上调至180亿美元。我们预测定制芯片收入为110亿美元。"}},
                {"evidence_id": "ev-unread", "value": {"content_tier": "LICENSED_API_CONTENT",
                    "content": "不应向未查询的任务回显。"}},
                {"evidence_id": "ev-title", "value": {"content_tier": "LEAD_ONLY",
                    "content": "标题不是许可正文。"}},
            ]}
            gate["bundle_hash"] = canonical_hash(gate)
            (root / "evidence/gate.json").write_text(json.dumps(gate))
            event = {"event_type": "mcp_tool_result", "tool": "fixture_evidence.query",
                     "run_id": "run", "invocation_id": "invocation", "agent": "runtime_company_analyst",
                     "evidence_ids": ["ev-note", "ev-title"]}
            event["event_hash"] = canonical_hash(event)
            events = root / "events/mcp/events.jsonl"
            events.write_text(json.dumps(event) + "\n")
            packet = {"task": {
                "run_id": "run", "invocation_id": "invocation", "agent": "runtime_company_analyst",
                "capability": "RESEARCH_REPORT", "submission_version": VERSION,
                "source_evidence_review": "queried-source-excerpt-review/1.0.0",
                "allowed_evidence_ids": ["ev-note", "ev-unread", "ev-title"],
            }, "reference_map": {"evidence": {
                "e.note": "ev-note", "e.unread": "ev-unread", "e.title": "ev-title",
            }}}
            draft = {"claims": [{"claim_id": "forecast", "statement": "180亿美元为作者预测。",
                                 "evidence_refs": ["e.note", "e.unread", "e.title"]}]}
            review = _source_evidence_review(root, draft, packet, "secret-token")
            self.assertEqual((review["status"], review["pair_count"]), ("AVAILABLE", 1))
            self.assertEqual(review["pairs"][0]["evidence_ref"], "e.note")
            self.assertIn("管理层将", review["pairs"][0]["source_excerpt"])
            self.assertIn("我们预测", review["pairs"][0]["source_excerpt"])
            self.assertNotIn("不应向未查询", json.dumps(review, ensure_ascii=False))
            self.assertNotIn("标题不是", json.dumps(review, ensure_ascii=False))
            self.assertNotIn("secret-token", json.dumps(review, ensure_ascii=False))
            self.assertLessEqual(len(json.dumps(review, ensure_ascii=False).encode("utf-8")), 12 * 1024)
            self.assertEqual(_source_evidence_review(root, draft, {
                **packet, "task": {**packet["task"], "source_evidence_review": None},
            }, "secret-token")["status"], "NOT_AVAILABLE")
            other = {**event, "invocation_id": "other"}
            other["event_hash"] = canonical_hash({k: v for k, v in other.items() if k != "event_hash"})
            events.write_text(json.dumps(other) + "\n")
            self.assertEqual(_source_evidence_review(root, draft, packet, "secret-token")["status"],
                             "NOT_AVAILABLE")
            events.write_text(json.dumps({**event, "event_hash": "tampered"}) + "\n")
            self.assertEqual(_source_evidence_review(root, draft, packet, "secret-token")["status"],
                             "NOT_AVAILABLE")
            events.write_text(json.dumps(event) + "\n")
            gate["allowed_evidence"][0]["value"]["content"] = "管理层指引。" * 1000
            gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
            (root / "evidence/gate.json").write_text(json.dumps(gate))
            bounded = _source_evidence_review(root, draft, packet, "secret-token")
            self.assertTrue(bounded["pairs"][0]["source_excerpt_truncated"])
            self.assertLessEqual(len(json.dumps(bounded, ensure_ascii=False).encode("utf-8")), 12 * 1024)


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
        return _research_report_monetary_findings(
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
        from product.runtime.codex_hook_recorder import _monetary_repetition_context
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
        self.assertEqual(_monetary_repetition_context(draft, findings), expected)
        native = json.loads(original)
        native["claims"][0].pop("statement")
        native["claims"][0].update(core_statement="$1.4 billion", research_relation_clauses=[
            {"relation_statement": "and $2 billion"}])
        self.assertEqual(_monetary_repetition_context(native, findings), expected)
        for wrong in ([], [{**findings[0], "code": "OTHER"}],
                      [{**findings[0], "path": "claims[99].statement"}],
                      [{**findings[0], "amount_index": -1}]):
            self.assertEqual(_monetary_repetition_context(draft, wrong), [])
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
        findings = _research_report_monetary_findings(
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
        self.assertEqual([x["amount_index"] for x in _research_report_monetary_findings(
            {"claims": [{**self.claim, "evidence_refs": [self.short_id, "e.other"]}]},
            task=task, gate=gate, reference_packet=packet, selected_upstream=[],
        )], [1, 2])
        self.assertEqual(_research_report_monetary_findings(
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
            _research_report_monetary_findings(
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
        findings = _research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[],
        )
        self.assertEqual([(item["path"], item["identifier"]) for item in findings],
                         [("claims[0].statement", self.short_id)])
        self.assertNotIn("管理层", json.dumps(findings, ensure_ascii=False))
        self.assertEqual(_research_report_monetary_findings(
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
        findings = _research_report_monetary_findings(
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
        self.assertEqual(len(_research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[],
        )), 2)
        gate = {"allowed_evidence": [licensed, other]}
        gate["bundle_hash"] = canonical_hash(gate)
        self.assertEqual(_research_report_monetary_findings(
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
                self.assertEqual(_research_report_monetary_findings(
                    {"claims": [claim]}, task=task, gate=gate,
                    reference_packet=packet, selected_upstream=[],
                ), [])
        source_english = {**other, "value": {**other["value"],
            "content": "2.6 billion USD in cash."}}
        gate = {"allowed_evidence": [licensed, source_english]}
        gate["bundle_hash"] = canonical_hash(gate)
        self.assertEqual([item["amount_index"] for item in _research_report_monetary_findings(
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
        self.assertEqual(_research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[selection],
        ), [])
        competitor = {**other, "value": {"content_tier": "LICENSED_API_CONTENT",
            "content": "另一个来源也写$26亿现金。"}}
        gate = {"allowed_evidence": [licensed, competitor]}
        gate["bundle_hash"] = canonical_hash(gate)
        self.assertEqual([item["amount_index"] for item in _research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[],
        )], [1])


class ResearchSubmissionTests(unittest.TestCase):
    """v3–v5 用测试专用历史包构造器验证读取；当前 v6 用真实 MCP。

    历史构造/辅助检查正例不计作新提交或模型执行证明。
    """
    def test_new_structured_research_run_uses_short_receipt_protocol_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            prepare = fixtures.prepare_multidimensional_stage_run

            def structured(*args, **kwargs):
                return prepare(*args, **kwargs, structured_report_submission=True)

            with patch.object(fixtures, "prepare_multidimensional_stage_run", side_effect=structured):
                _, _, task = references.ReferenceBoundaryTests().prepare_with_document(Path(directory))
            self.assertEqual(task["submission_version"], BOUNDED_REVISION_VERSION)

    def test_v3_document_choice_is_assembled_and_saved_with_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory))
            selected_id = task["allowed_documents"][0]["document_id"]
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            selected_ref = next(key for key, value in packet["reference_map"]["documents"].items() if value == selected_id)
            for serialize in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
                context = json.loads(serialize(packet))
                guide = context["submission_contract"]["draft_format_guide"]
                self.assertIn(selected_ref, guide["properties"]["document_selections"]["items"]["enum"])
                self.assertNotIn("documents", guide["required"])
            draft.pop("documents")
            draft["document_selections"] = [selected_ref]
            receipt = self.submit(StatelessFixtureTools(default_run_dir=run), task, draft)
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = receipt["final_message"]
            report, _, accepted = store_historical_report_fixture(run, task, receipt["final_message"])
            self.assertEqual(report["documents"], [task["allowed_documents"][0]])
            self.assertNotIn("document_selections", report)
            self.assertEqual(selected_calculations_for_report(run, report), [])
            marker = json.loads(accepted.read_text())
            self.assertEqual(marker["report_hash"], report["report_hash"])
            marker["report_hash"] = "tampered"
            accepted.write_text(json.dumps(marker))
            with self.assertRaisesRegex(ValueError, "ACCEPTED_RECORD_INVALID"):
                selected_calculations_for_report(run, report)

    def test_v3_document_mixed_and_unknown_choices_are_rejected(self):
        for defect in ("mixed", "unknown", "duplicate"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                f, run, task, env, draft = self.submit_and_start(Path(directory))
                identifier = task["allowed_documents"][0]["document_id"]
                if defect != "mixed":
                    draft.pop("documents")
                draft["document_selections"] = (
                    [identifier] if defect == "mixed" else
                    ["unknown-document"] if defect == "unknown" else [identifier, identifier]
                )
                tools = StatelessFixtureTools(default_run_dir=run)
                with self.assertRaisesRegex(ValueError, "RESEARCH_SUBMISSION_DOCUMENT") as error:
                    self.submit(tools, task, draft)
                if defect == "unknown":
                    self.assertIn("unknown-document", str(error.exception))
                self.assertFalse((_directory(run, task["invocation_id"], create=False) / "1.json").exists())
                draft["document_selections"] = [identifier]
                draft.pop("documents", None)
                receipt = self.submit(tools, task, draft)
                self.assertEqual(receipt["submission"], 1)

    def test_v3_document_precheck_keeps_credential_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, task, _, draft = self.submit_and_start(Path(directory))
            from product.runtime.research_submission import _selected_documents
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            selected = [item["document_id"] for item in task["allowed_documents"]]
            self.assertEqual([item["document_id"] for item in _selected_documents(
                {"document_selections": selected}, packet, selected,
            )], selected)
            draft.pop("documents")
            draft["document_selections"] = ["wrong-document-id"]
            tools = StatelessFixtureTools(default_run_dir=run)
            with self.assertRaisesRegex(ValueError, "RESEARCH_SUBMISSION_LEGACY_READ_ONLY") as error:
                tools.research_report_submit(invocation_id=task["invocation_id"], draft=draft,
                                             submission_token="invalid")
            self.assertNotIn("wrong-document-id", str(error.exception))
            self.assertFalse((_directory(run, task["invocation_id"], create=False) / "1.json").exists())

    def test_v3_selected_upstream_calculation_survives_save_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            source_task = next(item for item in index["tasks"] if item["capability"] == "FUNDAMENTAL_EVENT")
            source_path = next((run / "research/reports").glob("*/dimension-report.json"))
            source = json.loads(source_path.read_text())
            calculation_id = "synthetic_ratio_1"
            evidence_ids = source_task["allowed_evidence_ids"][:2]
            inputs = {"run_id": source_task["run_id"], "agent": source_task["agent"],
                      "invocation_id": source_task["invocation_id"],
                      "calculation_id": calculation_id, "operation": "ratio",
                      "evidence_ids": evidence_ids}
            output = {"run_id": source_task["run_id"], "calculation_id": calculation_id,
                      "operation": "ratio", "evidence_ids": evidence_ids, "value": "5",
                      "calculation_hash": canonical_hash({"test": calculation_id})}
            event = {**inputs, "tool": "fixture_math.calculate",
                     "input_hash": canonical_hash(inputs), "output_hash": canonical_hash(output)}
            event["event_hash"] = canonical_hash(event)
            receipt = {**inputs, "output": output, "tool_event_hash": event["event_hash"]}
            receipt["receipt_hash"] = canonical_hash(receipt)
            second_id = "synthetic_ratio_2"
            second_inputs = {**inputs, "calculation_id": second_id}
            second_output = {**output, "calculation_id": second_id,
                             "amounts": {"current": "5", "previous": "4"}}
            second_event = {**second_inputs, "tool": "fixture_math.calculate",
                            "input_hash": canonical_hash(second_inputs),
                            "output_hash": canonical_hash(second_output)}
            second_event["event_hash"] = canonical_hash(second_event)
            second_receipt = {**second_inputs, "output": second_output,
                              "tool_event_hash": second_event["event_hash"]}
            second_receipt["receipt_hash"] = canonical_hash(second_receipt)
            ledger_ref = source_task["calculation_ledger_ref"]
            (run / ledger_ref).write_text(json.dumps(receipt) + "\n" + json.dumps(second_receipt) + "\n")
            events = run / "events/mcp/events.jsonl"
            events.parent.mkdir(parents=True, exist_ok=True)
            with events.open("a") as stream:
                stream.write(json.dumps(event) + "\n" + json.dumps(second_event) + "\n")
            source["calculations"] = [
                {"calculation_id": identifier, "method": "ratio", "value": "5",
                 "unit": "ratio", "input_evidence_refs": evidence_ids,
                 "artifact_ref": ledger_ref}
                for identifier in (calculation_id, second_id)
            ]
            source["artifact_refs"].append(ledger_ref)
            source["claims"][0]["calculation_refs"] = [calculation_id, second_id]
            source["report_hash"] = canonical_hash({
                key: value for key, value in source.items() if key != "report_hash"
            })
            source_path.write_text(json.dumps(source))
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            dependency = packet["dependency_reports"][0]
            self.assertEqual(dependency["verified_calculations"][0]["calculation_id"], calculation_id)
            draft["status"] = "LOW_CONFIDENCE"
            draft["sufficiency"] = "PARTIAL"
            draft["claims"] = [{"claim_id": "local_ratio", "question": "经营情况？",
                                "statement": "上游比值提供有限参考。", "kind": "INTERPRETATION",
                                "evidence_refs": ["ev-issuer-body"],
                                "research_claim_refs": [next(iter(packet["reference_map"]["claims"]))],
                                "document_refs": [], "assumption_ids": [], "calculation_refs": []}]
            choice = {"claim_id": "local_ratio", "report_id": source["report_id"],
                      "source_claim_id": source["claims"][0]["claim_id"],
                      "calculation_id": calculation_id}
            draft["upstream_calculation_selections"] = [choice, {
                **choice, "calculation_id": second_id,
            }]
            preview_selections = []
            def capture_preview(*args, **kwargs):
                preview_selections.extend(kwargs["selected_upstream"])
                return []
            with patch("product.runtime.codex_hook_recorder._research_report_monetary_findings",
                       side_effect=capture_preview):
                receipt = self.submit(StatelessFixtureTools(default_run_dir=run), task, draft)
            self.assertEqual([item["verified_output"] for item in preview_selections],
                             [output, second_output])
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = receipt["final_message"]
            report, fixture_output, _ = store_historical_report_fixture(run, task, receipt["final_message"])
            selected = selected_calculations_for_report(run, report)
            self.assertEqual(len(selected), 2)
            self.assertEqual(selected[0]["verified_output"], output)
            self.assertEqual(selected[1]["verified_output"], second_output)
            markdown = Path(fixture_output["markdown"]).read_text()
            self.assertIn("上游计算", markdown)
            self.assertIn(calculation_id, markdown)
            # 仅证明冻结历史包可读，不冒充当前 Hook 执行证明。
            copied = Path(directory) / "copied-package"
            for relative in ("research/reports", "research/submissions",
                             "research/calculations", "events/mcp"):
                shutil.copytree(run / relative, copied / relative)
            copied_gate = json.loads((run / "evidence/gate.json").read_text())
            copied_gate["source_gates"] = [{
                "role": "BASE_MULTIDIMENSIONAL", "gate_hash": copied_gate["bundle_hash"],
            }]
            copied_gate["bundle_hash"] = canonical_hash({
                key: value for key, value in copied_gate.items() if key != "bundle_hash"
            })
            (copied / "evidence").mkdir()
            (copied / "evidence/gate.json").write_text(json.dumps(copied_gate))
            self.assertEqual(
                [item["verified_output"] for item in selected_calculations_for_report(copied, report)],
                [output, second_output],
            )
            drifted_gate = {**copied_gate, "decision_cutoff": "2026-09-12T12:00:00Z"}
            (copied / "evidence/gate.json").write_text(json.dumps(drifted_gate))
            with self.assertRaisesRegex(ValueError, "COPIED_GATE_INVALID"):
                selected_calculations_for_report(copied, report)
            drifted_gate["bundle_hash"] = canonical_hash({
                key: value for key, value in drifted_gate.items() if key != "bundle_hash"
            })
            (copied / "evidence/gate.json").write_text(json.dumps(drifted_gate))
            with self.assertRaisesRegex(ValueError, "COPIED_GATE_INVALID"):
                selected_calculations_for_report(copied, report)
            (copied / "evidence/gate.json").write_text(json.dumps(copied_gate))
            copied_events = (copied / "events/mcp/events.jsonl").read_text()
            (copied / "events/mcp/events.jsonl").write_text(copied_events.replace(
                '"output_hash": "' + event["output_hash"] + '"',
                '"output_hash": "tampered"', 1,
            ))
            with self.assertRaisesRegex(ValueError, "COPIED_EVENT_INVALID"):
                selected_calculations_for_report(copied, report)
            (copied / "events/mcp/events.jsonl").write_text(copied_events)
            accepted_ref = str(_directory(copied, report["invocation_id"], create=False).relative_to(copied) / "accepted.json")
            (copied / "research/holding-research-bundle.json").write_text(json.dumps({
                "artifact_refs": [accepted_ref],
            }))
            copied_marker = copied / accepted_ref
            marker_bytes = copied_marker.read_bytes()
            copied_marker.unlink()
            with self.assertRaisesRegex(ValueError, "COPIED_RECORD_MISSING"):
                selected_calculations_for_report(copied, report)
            copied_marker.write_bytes(marker_bytes)
            invalid = {**draft, "upstream_calculation_selections": [
                {**choice, "source_claim_id": "another_claim"}]}
            with self.assertRaisesRegex(ValueError, "CALCULATION_CLAIM_MISMATCH"):
                _assemble_v3_draft(invalid, packet)
            invalid["upstream_calculation_selections"] = [{**choice, "calculation_id": "other_calculation"}]
            with self.assertRaisesRegex(ValueError, "CALCULATION_NOT_VERIFIED"):
                _assemble_v3_draft(invalid, packet)
            invalid["upstream_calculation_selections"] = [{**choice, "report_id": "another_report"}]
            with self.assertRaisesRegex(ValueError, "CALCULATION_CLAIM_MISMATCH"):
                _assemble_v3_draft(invalid, packet)
            original_ledger = (run / ledger_ref).read_text()
            (run / ledger_ref).write_text("tampered\n")
            with self.assertRaises(ValueError):
                selected_calculations_for_report(run, report)
            (run / ledger_ref).write_text(original_ledger)
            gate_path = run / "evidence/gate.json"
            gate = json.loads(gate_path.read_text())
            gate["decision_cutoff"] = "2026-09-12T12:00:00Z"
            gate["bundle_hash"] = canonical_hash({
                key: value for key, value in gate.items() if key != "bundle_hash"
            })
            gate_path.write_text(json.dumps(gate))
            with self.assertRaisesRegex(ValueError, "SUBMISSION_GATE_BINDING_INVALID"):
                selected_calculations_for_report(run, report)

    def token(self, run, task):
        packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
        return packet["submission_access"]["token"]

    def submit(self, tools, task, draft):
        if task.get("submission_version") in {VERSION, FORMAL_VERSION, SHORT_RECEIPT_VERSION}:
            from tests.historical_submission_fixture import store_historical_submission_fixture
            return store_historical_submission_fixture(tools, task, draft)
        result = tools.research_report_submit(invocation_id=task["invocation_id"], draft=draft,
                                             submission_token=self.token(tools.default_run_dir, task))
        from product.runtime.fixture_mcp import _write_event
        _write_event(tools.dynamic_event_log, tools.events[-1])
        return result

    def native_draft(self, draft):
        # 测试作者显式提供 v6 输入，不在产品中偷偷修旧草稿。
        draft = json.loads(json.dumps(draft))
        for field in ("documents", "calculations", "artifact_refs"):
            draft.pop(field)
        draft.update(document_selections=[], calculation_selections=[])
        return draft

    def test_malformed_research_refs_leave_preview_unevaluated_for_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory))
            draft["claims"] = [{
                "claim_id": "malformed_refs", "question": "来源结论？",
                "statement": "来源提供有限背景。", "kind": "INTERPRETATION",
                "evidence_refs": [], "research_claim_refs": None,
                "document_refs": [], "assumption_ids": [], "calculation_refs": [],
            }]
            receipt = self.submit(StatelessFixtureTools(default_run_dir=run), task, draft)
            self.assertEqual(receipt["monetary_review"], {
                "status": "NOT_EVALUATED", "findings": [],
            })
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = receipt["final_message"]
            with self.assertRaises((TypeError, ValueError)):
                read_historical_report_fixture(run, task, receipt["final_message"])

    def test_monetary_review_is_bounded_without_changing_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory))
            findings = [{
                "code": "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED",
                "path": f"claims[{index}].statement", "identifier": "e.short",
                "amount_index": index, "source_unit": "亿美元",
                "reported_unit": "billion USD",
            } for index in range(40)]
            tools = StatelessFixtureTools(default_run_dir=run)
            with patch("product.runtime.codex_hook_recorder._research_report_monetary_findings",
                       return_value=findings):
                result = self.submit(tools, task, draft)
            self.assertEqual(result["monetary_review"]["status"], "LOCATED")
            self.assertEqual(result["monetary_review"]["finding_count"], 40)
            self.assertEqual(len(result["monetary_review"]["findings"]), 32)
            self.assertTrue(result["monetary_review"]["truncated"])
            self.assertEqual(tools.events[-1]["monetary_finding_count"], 40)
            self.assertEqual(json.loads(result["final_message"]), {
                "submission": 1, "content_hash": result["content_hash"],
            })
            self.assertNotIn("submission_token", json.dumps(tools.events[-1]))

    def test_citation_review_echoes_verified_target_without_changing_receipt_or_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory))
            self.assertEqual(task["source_evidence_review"], "queried-source-excerpt-review/1.0.0")
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            short_ref, mapped = next(iter(packet["reference_map"]["claims"].items()))
            dependency = next(report for report in packet["dependency_reports"]
                              if report["report_id"] == mapped["report_id"])
            upstream = next(claim for claim in dependency["claims"]
                            if claim["claim_id"] == mapped["claim_id"])
            draft["claims"] = [{
                "claim_id": "local_citation_review", "question": "上游结论如何影响本研究？",
                "statement": "上游结论只提供有限背景，仍需本段独立核验。",
                "kind": "INTERPRETATION", "evidence_refs": [],
                "research_claim_refs": [short_ref], "document_refs": [],
                "assumption_ids": [], "calculation_refs": [],
            }]
            tools = StatelessFixtureTools(default_run_dir=run)
            first = self.submit(tools, task, draft)
            self.assertIn(first["monetary_review"]["status"], {"NONE_LOCATED", "NOT_EVALUATED"})
            self.assertEqual(tools.events[-1]["citation_pair_count"], 1)
            self.assertEqual(tools.events[-1]["monetary_finding_count"], 0)
            self.assertEqual(tools.events[-1]["source_review_pair_count"], 0)
            self.assertEqual(first["source_evidence_review"]["status"], "NOT_AVAILABLE")
            self.assertIsInstance(tools.events[-1]["review_hash"], str)
            self.assertEqual(json.loads(first["final_message"]), {
                "submission": 1, "content_hash": first["content_hash"],
            })
            review = first["citation_review"]
            self.assertEqual((review["pair_count"], review["returned_pair_count"], review["truncated"]),
                             (1, 1, False))
            self.assertEqual(review["pairs"], [{
                "claim_id": draft["claims"][0]["claim_id"],
                "current_statement": draft["claims"][0]["statement"],
                "research_claim_ref": short_ref,
                "resolution": "VERIFIED_TARGET_NOT_SEMANTICALLY_REVIEWED",
                "upstream_report_id": dependency["report_id"],
                "upstream_report_hash": dependency["report_hash"],
                "upstream_claim_id": upstream["claim_id"],
                "upstream_statement": upstream["statement"],
            }])
            self.assertNotIn(self.token(run, task), json.dumps(first, ensure_ascii=False))
            first_path = _directory(run, task["invocation_id"]) / "1.json"
            original = first_path.read_bytes()
            self.assertEqual(json.loads(original)["draft"], draft)
            draft["claims"] = []
            second = self.submit(tools, task, draft)
            self.assertEqual(second["citation_review"]["pairs"], [])
            self.assertEqual(first_path.read_bytes(), original)
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = second["final_message"]
            report, _, _, _ = read_historical_report_fixture(run, task, second["final_message"])
            self.assertEqual(report["claims"], [])
            with self.assertRaisesRegex(ValueError, "LIMIT_EXHAUSTED"):
                self.submit(tools, task, draft)

    def test_citation_review_unknown_and_bounded_pairs_are_not_semantic_approval(self):
        token = "test-token-not-to-echo-12345678901234567890"
        packet = {
            "dependency_reports": [{
                "report_id": "upstream", "report_hash": "verified-hash", "claims": [{
                    "claim_id": "source-claim", "statement": "上游只陈述经营事实。",
                }],
            }],
            "reference_map": {"claims": {"c.verified.1": {
                "report_id": "upstream", "claim_id": "source-claim",
            }}},
        }
        draft = {"claims": [{
            "claim_id": "local", "research_claim_refs": ["c.verified.1"] * 9,
        }]}
        review = _citation_review(draft, packet, token)
        self.assertEqual((review["pair_count"], review["returned_pair_count"]), (9, 9))
        self.assertTrue(all(pair["upstream_statement"] == "上游只陈述经营事实。"
                            for pair in review["pairs"]))
        self.assertTrue(all(pair["current_statement"] == "[REDACTED]" for pair in review["pairs"]))
        draft["claims"][0]["statement"] = "本段只陈述不同主题。"
        review = _citation_review(draft, packet, token)
        self.assertTrue(all(pair["current_statement"] == "本段只陈述不同主题。"
                            for pair in review["pairs"]))
        draft["claims"][0]["research_claim_refs"].append("c.unknown")
        with self.assertRaisesRegex(ValueError, "MULTIDIMENSIONAL_REFERENCE_UNKNOWN"):
            _citation_review(draft, packet, token)
        draft["claims"][0]["research_claim_refs"] = ["c.verified.1"] * 33
        bounded = _citation_review(draft, packet, token)
        self.assertEqual((bounded["pair_count"], bounded["returned_pair_count"], bounded["truncated"]),
                         (33, 32, True))
        self.assertIn("回查本任务已交付的上游依赖", bounded["rule"])
        local = _citation_review({"claims": [{
            "claim_id": "c.verified.1", "research_claim_refs": ["c.verified.1"],
        }]}, packet, token)
        self.assertEqual(local["pairs"][0]["resolution"], "LOCAL_CLAIM_NOT_UPSTREAM")
        self.assertNotIn("upstream_statement", local["pairs"][0])
        packet["dependency_reports"][0]["claims"][0]["statement"] = "长" * 9000
        byte_bounded = _citation_review({"claims": [{
            "claim_id": "local", "research_claim_refs": ["c.verified.1"],
        }]}, packet, token)
        self.assertTrue(byte_bounded["truncated"])
        self.assertLessEqual(len(json.dumps(byte_bounded, ensure_ascii=False).encode()),
                             MAX_CITATION_REVIEW_BYTES)
        packet["dependency_reports"][0]["claims"][0]["statement"] = token
        redacted = _citation_review({"claims": [{
            "claim_id": "local", "research_claim_refs": ["c.verified.1"],
        }]}, packet, token)
        self.assertEqual(redacted["pairs"][0]["upstream_statement"], "[REDACTED]")
        self.assertNotIn(token, json.dumps(redacted))

    def test_unknown_short_citation_is_rejected_before_consuming_submit_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, task, _, draft = self.submit_and_start(Path(directory))
            tools = StatelessFixtureTools(default_run_dir=run)
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            valid = next(iter(packet["reference_map"]["claims"]))
            for refs in (["c.not-in-map"], [valid] * 33 + ["c.not-in-map"]):
                draft["claims"] = [{"claim_id": "local", "research_claim_refs": refs}]
                with self.assertRaisesRegex(ValueError, "MULTIDIMENSIONAL_REFERENCE_UNKNOWN"):
                    self.submit(tools, task, draft)
                self.assertFalse((run / "research/submissions").exists())
            draft["claims"] = []
            self.assertEqual(self.submit(tools, task, draft)["submission"], 1)

    def test_wrong_credentials_cannot_create_or_consume_slots(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            f, run, task, env, draft = self.submit_and_start(Path(first), version=BOUNDED_REVISION_VERSION)
            _, other_run, other_task, _, _ = self.submit_and_start(Path(second), version=BOUNDED_REVISION_VERSION)
            draft = self.native_draft(draft)
            token = self.token(run, task)
            other_token = self.token(other_run, other_task)
            self.assertNotEqual(token, other_token)
            tools = StatelessFixtureTools(default_run_dir=run)
            # A shared caller knows the correct target ID; that alone must not write.
            for invalid in (None, "wrong-task-token", other_token, {}, 1, "非本任务"):
                with self.subTest(credential_type=type(invalid).__name__):
                    with self.assertRaisesRegex(ValueError, "CREDENTIAL_INVALID"):
                        tools.research_report_submit(invocation_id=task["invocation_id"],
                                                     draft=draft, submission_token=invalid)
                    self.assertFalse((run / "research/submissions").exists())
            with self.assertRaisesRegex(ValueError, "CREDENTIAL_IN_DRAFT"):
                self.submit(tools, task, {**draft, "summary": token})
            self.assertFalse((run / "research/submissions").exists())
            first_receipt = self.submit(tools, task, draft)
            self.assertEqual(first_receipt["submission"], 1)
            for _ in range(3):
                with self.assertRaisesRegex(ValueError, "CREDENTIAL_INVALID"):
                    tools.research_report_submit(invocation_id=task["invocation_id"], draft=draft)
            # 首稿无缺陷时没有局部修订许可，不能任意提交第二整稿。
            with self.assertRaisesRegex(ValueError, "REVISION"):
                self.submit(tools, task, draft)

    def test_only_target_context_receives_token_and_packet_is_private(self):
        from product.runtime.multidimensional_stage import build_multidimensional_stage_prompt
        with tempfile.TemporaryDirectory() as directory:
            _, run, target = self.prepare(Path(directory), version=BOUNDED_REVISION_VERSION)
            token = self.token(run, target)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            self.assertNotIn(token, json.dumps(index))
            self.assertNotIn(token, build_multidimensional_stage_prompt(fixtures.ROOT, run))
            for task in index["tasks"]:
                packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                serializers = [serialize_multidimensional_model_context]
                if task["capability"] in {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT"}:
                    serializers.append(serialize_multidimensional_initial_context)
                for serializer in serializers:
                    context = json.loads(serializer(packet))
                    self.assertNotIn("submission_access", context)
                    self.assertEqual(token in json.dumps(context), task == target)
                    if task == target:
                        self.assertEqual(context["submission_contract"]["submission_token"], token)
                if task == target:
                    self.assertEqual((run / task["packet_path"]).stat().st_mode & 0o777, 0o600)

    def test_rejected_stdio_calls_redact_credentials_and_leave_slots_free(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, task, _, draft = self.submit_and_start(Path(directory), version=BOUNDED_REVISION_VERSION)
            draft = self.native_draft(draft)
            token = self.token(run, task)
            wrong_token = "wrong-private-submission-token-not-for-logs"
            tools = StatelessFixtureTools(default_run_dir=run)
            requests = [
                {"jsonrpc": "2.0", "id": number, "method": "tools/call", "params": {
                    "name": "research_report_submit", "arguments": {
                        "invocation_id": task["invocation_id"], "submission_token": credential, "draft": body}}}
                for number, credential, body in (
                    (1, wrong_token, draft), (2, token, {**draft, "summary": token}))
            ]
            stdout = io.StringIO()
            log = run / "events/mcp/rejected-submission-test.jsonl"
            with patch("sys.stdin", io.StringIO('\n'.join(json.dumps(x) for x in requests))), patch("sys.stdout", stdout):
                self.assertEqual(serve_stdio(tools_override=tools, event_log=log), 0)
            responses = [json.loads(x) for x in stdout.getvalue().splitlines()]
            self.assertEqual([r["error"]["message"] for r in responses],
                             ["RESEARCH_SUBMISSION_CREDENTIAL_INVALID", "RESEARCH_SUBMISSION_CREDENTIAL_IN_DRAFT"])
            for credential in (token, wrong_token):
                self.assertNotIn(credential, stdout.getvalue())
                self.assertNotIn(credential, log.read_text())
            self.assertFalse((run / "research/submissions").exists())
            self.assertEqual(self.submit(tools, task, draft)["submission"], 1)

    def test_receipt_binds_exact_draft_not_just_slot(self):
        for defect in ("wrong_hash", "wrong_slot", "legacy_receipt"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                f, run, task, env, draft = self.submit_and_start(Path(directory))
                tools = StatelessFixtureTools(default_run_dir=run)
                first = self.submit(tools, task, draft)
                second = self.submit(tools, task, {**draft, "summary": "第二份不同的模拟草稿"})
                receipt = json.loads(first["final_message"])
                if defect == "wrong_hash":
                    receipt["content_hash"] = second["content_hash"]
                elif defect == "wrong_slot":
                    receipt["submission"] = 2
                else:
                    receipt.pop("content_hash")
                payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
                payload["last_assistant_message"] = json.dumps(receipt)
                with self.assertRaisesRegex(ValueError, "RECEIPT"):
                    read_historical_report_fixture(run, task, json.dumps(receipt))

    def test_legacy_artifact_resolves_but_cannot_accept_new_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, task, _, draft = self.submit_and_start(Path(directory))
            # Explicit synthetic historical fixture, never migrate a real run.
            index_path = run / "research/dispatch-index.json"
            index = json.loads(index_path.read_text())
            target = next(t for t in index["tasks"] if t["task_id"] == task["task_id"])
            packet_path = run / target["packet_path"]
            packet = json.loads(packet_path.read_text())
            packet["task"]["submission_version"] = LEGACY_VERSION
            packet.pop("submission_access")
            packet_path.write_text(json.dumps(packet))
            target["submission_version"] = LEGACY_VERSION
            target["packet_hash"] = canonical_hash(packet)
            index["index_hash"] = canonical_hash({k: v for k, v in index.items() if k != "index_hash"})
            index_path.write_text(json.dumps(index))
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            stored = {"binding": {"version": LEGACY_VERSION, "identity": packet["identity"],
                                  "packet_hash": canonical_hash(packet)}, "draft": draft}
            stored["content_hash"] = canonical_hash(stored)
            path = _directory(run, task["invocation_id"]) / "1.json"
            path.write_text(json.dumps(stored))
            before = path.read_bytes()
            record = {"identity_binding": {"status": "BOUND"}, "trusted_task_binding": packet["identity"]}
            restored = resolve(run, {"last_assistant_message": '{"submission":1}'}, record, 1)
            restored_draft = json.loads(restored["last_assistant_message"])
            for key in draft:
                self.assertEqual(restored_draft[key], draft[key])
            with self.assertRaisesRegex(ValueError, "LEGACY_READ_ONLY"):
                StatelessFixtureTools(default_run_dir=run).research_report_submit(
                    invocation_id=task["invocation_id"], draft=draft)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse(path.with_name("2.json").exists())

    def test_task_submission_and_semantic_guidance_are_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, _ = self.prepare(Path(directory), version=BOUNDED_REVISION_VERSION)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            tools = StatelessFixtureTools(default_run_dir=run)
            description = next(t["description"] for t in tools.available_tools()
                               if t["name"] == "research_report_submit")
            self.assertIn("RESEARCH_REPORT", description)
            self.assertIn("submission_contract", description)
            self.assertIn("allowed_paths", description)
            for task in index["tasks"]:
                packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                before = json.dumps(packet, sort_keys=True)
                serializers = [serialize_multidimensional_model_context]
                if task["capability"] in {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT"}:
                    serializers.append(serialize_multidimensional_initial_context)
                for serializer in serializers:
                    context = json.loads(serializer(packet))
                    rule = context["output_submission_guidance"]["instruction"]
                    self.assertIn("最终完整 JSON", rule)
                    self.assertIn("真实取证失败及其影响仍须保留", rule)
                    self.assertEqual("submission_contract" in context, task["capability"] == "RESEARCH_REPORT")
                    self.assertEqual("technical_summary_guidance" in context, task["capability"] == "TECHNICAL_STRUCTURE")
                    if task["capability"] == "TECHNICAL_STRUCTURE":
                        check = context["technical_summary_guidance"]["self_check"]
                        self.assertIn("百分比与百分点", check)
                        self.assertIn("不自行设阈值或补算", check)
                        self.assertNotIn("209.82", check)
                self.assertEqual(json.dumps(packet, sort_keys=True), before)

    def test_industry_tool_rejection_does_not_break_original_output(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, _ = self.prepare(Path(directory))
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(t for t in index["tasks"] if t["capability"] == "INDUSTRY_COMPARISON")
            env = f.targeted_environment(run, task)
            handle_hook_event(f.dispatch_payload(task, parent="dependency-parent"), environ=env)
            handle_hook_event(f.start_payload(task, parent="dependency-parent", child="industry"), environ=env)
            draft = f.dimension_draft(task)
            original = json.dumps(draft, sort_keys=True)
            with self.assertRaisesRegex(ValueError, "NOT_ENABLED"):
                StatelessFixtureTools(default_run_dir=run).research_report_submit(
                    invocation_id=task["invocation_id"], draft=draft)
            record, _ = handle_hook_event(f.stop_payload(task, draft, parent="dependency-parent", child="industry"), environ=env)
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            self.assertEqual(json.dumps(draft, sort_keys=True), original)

    def test_launcher_enables_submission_only_explicitly(self):
        from product.runtime.nested_codex import build_nested_codex_command
        root = Path('/tmp/research-submission-command-test')
        args = dict(codex_binary="codex", product_root=fixtures.ROOT / "product", run_dir=root,
                    model="gpt-6-luna", sqlite_home=root / "sqlite", log_dir=root / "logs",
                    final_message_path=root / "final.json", hook_recorder_path=fixtures.ROOT / "product/runtime/codex_hook_recorder.py",
                    fixture_mcp_run_dir=root)
        for enabled in (False, True):
            command = build_nested_codex_command(**args, research_submission_enabled=enabled)
            config = next(x for x in command if x.startswith("mcp_servers.fixture_runtime="))
            self.assertEqual("research_report_submit" in config, enabled)

    def test_bad_receipts_symlink_and_untrusted_stop_do_not_save(self):
        for defect in ("missing", "mixed", "boolean", "symlink", "untrusted", "old_full_draft"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                f, run, task, env, draft = self.submit_and_start(Path(directory))
                tool = StatelessFixtureTools(default_run_dir=run)
                receipt = self.submit(tool, task, draft)
                path = _directory(run, task["invocation_id"]) / "1.json"
                if defect == "symlink":
                    target = path.with_name("original.json")
                    path.rename(target); path.symlink_to(target)
                message = {"missing": '{"submission":2}', "mixed": '{"submission":1,"summary":"extra"}',
                           "boolean": '{"submission":true}', "old_full_draft": json.dumps(draft)}.get(defect, receipt["final_message"])
                payload = f.stop_payload(task, {}, parent="dependency-parent", child="wrong" if defect == "untrusted" else "r")
                payload["last_assistant_message"] = message
                record, _ = handle_hook_event(payload, environ=env)
                self.assertEqual(record["output_capture"]["status"], "FAILED", record)
                self.assertNotEqual(record["output_capture"]["repair_state"], "REPAIR_REQUESTED")

    def prepare(self, root, enabled=True, *, version=VERSION, task_bound_tools=False):
        prepare = fixtures.prepare_multidimensional_stage_run
        def selected(*args, **kwargs):
            return prepare(*args, **kwargs, structured_report_submission=enabled, task_bound_tools=task_bound_tools)
        with patch.object(fixtures, "prepare_multidimensional_stage_run", side_effect=selected):
            with patch("product.runtime.research_submission.LATEST_VERSION", version):
                return references.ReferenceBoundaryTests().prepare_with_document(root)

    def submit_and_start(self, root, *, version=VERSION, task_bound_tools=False):
        f, run, task = self.prepare(root, version=version, task_bound_tools=task_bound_tools)
        env = f.targeted_environment(run, task)
        # 退役协议只构造历史读取向量，不为它制造当前执行事件。
        if version == BOUNDED_REVISION_VERSION:
            handle_hook_event(f.dispatch_payload(task, parent="dependency-parent"), environ=env)
            handle_hook_event(f.start_payload(task, parent="dependency-parent", child="r"), environ=env)
        draft = f.formal_dimension_draft(task)
        for key in ("run_id", "invocation_id", "agent"):
            draft.pop(key)
        return f, run, task, env, draft

    def test_v5_short_receipt_selects_exact_second_draft_without_hash_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(
                Path(directory), version=SHORT_RECEIPT_VERSION,
            )
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            self.assertEqual(task["submission_version"], SHORT_RECEIPT_VERSION)
            for serialize in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
                context = json.loads(serialize(packet))
                self.assertEqual(context["submission_contract"]["version"], SHORT_RECEIPT_VERSION)
                self.assertTrue(context["submission_contract"]["read_only"])
                self.assertIsNone(context["submission_contract"]["tool"])
                self.assertNotIn("submission_token", context["submission_contract"])
            reference = next(iter(packet["reference_map"]["claims"]))
            draft["claims"] = [{
                "claim_id": "v5_relation", "question": "来源观点如何关联上游？",
                "core_statement": "供应商提出一项有限观点。",
                "research_relation_clauses": [{
                    "research_claim_ref": reference,
                    "relation_statement": "上游经营事实仅提供背景，不验证该观点。",
                }],
                "kind": "INTERPRETATION", "evidence_refs": [],
                "research_claim_refs": [reference], "document_refs": [],
                "assumption_ids": [], "calculation_refs": [],
            }]
            tools = StatelessFixtureTools(default_run_dir=run)
            first = self.submit(tools, task, draft)
            updated = json.loads(json.dumps(draft))
            updated["claims"][0]["core_statement"] = "供应商提出一项已修订的有限观点。"
            second = self.submit(tools, task, updated)
            self.assertEqual((first["submission"], second["submission"]), (1, 2))
            self.assertRegex(first["final_message"], r"^r1\.[A-Za-z0-9_-]{24}$")
            self.assertRegex(second["final_message"], r"^r2\.[A-Za-z0-9_-]{24}$")
            self.assertNotIn(first["content_hash"], first["final_message"])
            self.assertNotIn(second["content_hash"], second["final_message"])
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = second["final_message"]
            report, _, accepted_path = store_historical_report_fixture(run, task, second["final_message"])
            self.assertIn("已修订的有限观点", report["claims"][0]["statement"])
            accepted = json.loads(accepted_path.read_text())
            self.assertEqual(accepted["submission_ref"], second["final_message"])
            self.assertEqual(accepted["submission_content_hash"], second["content_hash"])
            self.assertEqual(selected_calculations_for_report(run, report), [])

    def test_v5_rejects_wrong_credential_identity_old_receipt_and_foreign_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for defect, expected_error in (
                ("old-receipt", "RESEARCH_SUBMISSION_RECEIPT_REQUIRED"),
                ("foreign-reference", "RESEARCH_SUBMISSION_RECEIPT_INVALID"),
                ("tampered-content", "RESEARCH_SUBMISSION_BINDING_INVALID"),
            ):
                with self.subTest(defect=defect):
                    (root / defect).mkdir()
                    f, run, task, env, draft = self.submit_and_start(
                        root / defect, version=SHORT_RECEIPT_VERSION,
                    )
                    tools = StatelessFixtureTools(default_run_dir=run)
                    with self.assertRaisesRegex(ValueError, "LEGACY_READ_ONLY"):
                        tools.research_report_submit(
                            invocation_id=task["invocation_id"], draft=draft,
                            submission_token="wrong-token",
                        )
                    with self.assertRaisesRegex(ValueError, "DRAFT_IDENTITY_FORBIDDEN"):
                        self.submit(tools, task, {**draft, "agent": "runtime_skeptic"})
                    self.assertFalse((run / "research/submissions").exists())
                    original = self.submit(tools, task, draft)
                    if defect == "old-receipt":
                        message = json.dumps({"submission": 1, "content_hash": original["content_hash"]})
                    elif defect == "foreign-reference":
                        (root / "other").mkdir()
                        prepare = fixtures.prepare_multidimensional_stage_run

                        def other_task(*args, **kwargs):
                            kwargs["run_id"] = "foreign-run"
                            return prepare(*args, **kwargs)

                        with patch.object(fixtures, "prepare_multidimensional_stage_run", side_effect=other_task):
                            _, foreign_run, foreign_task, _, foreign_draft = self.submit_and_start(
                                root / "other", version=SHORT_RECEIPT_VERSION,
                            )
                        self.assertNotEqual(foreign_task["invocation_id"], task["invocation_id"])
                        foreign = self.submit(
                            StatelessFixtureTools(default_run_dir=foreign_run), foreign_task, foreign_draft,
                        )
                        message = foreign["final_message"]
                    else:
                        stored = _directory(run, task["invocation_id"]) / "1.json"
                        changed = json.loads(stored.read_text())
                        changed["draft"]["summary"] = "tampered"
                        stored.write_text(json.dumps(changed))
                        message = original["final_message"]
                    payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
                    payload["last_assistant_message"] = message
                    with self.assertRaisesRegex(ValueError, expected_error):
                        read_historical_report_fixture(run, task, message)
                    reports = [
                        json.loads(path.read_text())
                        for path in (run / "research/reports").glob("*/dimension-report.json")
                    ]
                    self.assertFalse(any(item["capability"] == "RESEARCH_REPORT" for item in reports))

    def test_v5_concurrent_submissions_get_distinct_slots_and_no_third_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, task, _, draft = self.submit_and_start(Path(directory), version=SHORT_RECEIPT_VERSION)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(
                    self.submit, StatelessFixtureTools(default_run_dir=run), task, draft,
                ) for _ in range(2)]
                receipts = [future.result() for future in futures]
            self.assertEqual({item["submission"] for item in receipts}, {1, 2})
            self.assertEqual(len({item["final_message"] for item in receipts}), 2)
            with self.assertRaisesRegex(ValueError, "LIMIT_EXHAUSTED"):
                self.submit(StatelessFixtureTools(default_run_dir=run), task, draft)

    def test_v5_valid_bearer_and_receipt_do_not_replace_trusted_stop_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(
                Path(directory), version=SHORT_RECEIPT_VERSION,
            )
            receipt = self.submit(StatelessFixtureTools(default_run_dir=run), task, draft)
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="not-the-started-child")
            payload["last_assistant_message"] = receipt["final_message"]
            record, _ = handle_hook_event(payload, environ=env)
            self.assertNotEqual((record.get("output_capture") or {}).get("status"), "SAVED")
            self.assertFalse((run / "research/submissions" / canonical_hash({
                "invocation_id": task["invocation_id"],
            })[:24] / "accepted.json").exists())

    def test_v4_formal_context_and_exact_agent_prose_survive_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory), version=FORMAL_VERSION)
            self.assertEqual(task["submission_version"], FORMAL_VERSION)
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            ref, target = next(iter(packet["reference_map"]["claims"].items()))
            for serializer in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
                context = json.loads(serializer(packet))
                self.assertEqual(context["submission_contract"]["version"], FORMAL_VERSION)
                claim_guide = context["submission_contract"]["draft_format_guide"]["$defs"]["claim"]
                self.assertIn("research_relation_clauses", claim_guide["required"])
                self.assertNotIn("statement", claim_guide["properties"])
            gate_path = run / "evidence/gate.json"
            original_gate = gate_path.read_bytes()
            gate = json.loads(original_gate)
            gate["decision_cutoff"] = "2020-01-01T00:00:00Z"
            gate["bundle_hash"] = canonical_hash({key: value for key, value in gate.items() if key != "bundle_hash"})
            gate_path.write_text(json.dumps(gate))
            with self.assertRaisesRegex(ValueError, "GATE_BINDING_INVALID"):
                self.submit(StatelessFixtureTools(default_run_dir=run), task, draft)
            gate_path.write_bytes(original_gate)
            source_path = next((run / "research/reports").glob("*/dimension-report.json"))
            original_dependency = source_path.read_bytes()
            source = json.loads(original_dependency)
            source["claims"][0]["statement"] = "tampered"
            source_path.write_text(json.dumps(source))
            with self.assertRaisesRegex(ValueError, "DEPENDENCY_REPORT_HASH_MISMATCH"):
                self.submit(StatelessFixtureTools(default_run_dir=run), task, draft)
            source_path.write_bytes(original_dependency)
            draft["claims"] = [{
                "claim_id": "valuation_relation", "question": "来源观点如何关联上游？",
                "core_statement": "供应商给出了独立估值观点。",
                "research_relation_clauses": [{"research_claim_ref": ref,
                    "relation_statement": "上游只提供历史经营事实，不验证该观点的公允价值。"}],
                "kind": "INTERPRETATION", "evidence_refs": [], "research_claim_refs": [ref],
                "document_refs": [], "assumption_ids": [], "calculation_refs": [],
            }]
            tools = StatelessFixtureTools(default_run_dir=run)
            self.assertNotIn("research_report_submit", [item["name"] for item in tools.available_tools()])
            with self.assertRaisesRegex(ValueError, "LEGACY_READ_ONLY"):
                tools.research_report_submit(invocation_id=task["invocation_id"], draft=draft,
                                             submission_token="wrong-token")
            self.assertFalse((run / "research/submissions").exists())
            receipt = self.submit(tools, task, draft)
            self.assertEqual(receipt["citation_review"]["pair_count"], 1)
            self.assertIn("上游只提供历史经营事实", receipt["citation_review"]["pairs"][0]["current_statement"])
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = receipt["final_message"]
            report, _, _ = store_historical_report_fixture(run, task, receipt["final_message"])
            self.assertEqual(report["claims"][0]["statement"],
                             "供应商给出了独立估值观点。 上游只提供历史经营事实，不验证该观点的公允价值。")
            self.assertEqual(report["claims"][0]["research_claim_refs"], [target["canonical_ref"]])
            self.assertNotIn("core_statement", report["claims"][0])
            stored = json.loads((_directory(run, task["invocation_id"]) / "1.json").read_text())
            self.assertEqual(stored["draft"], draft)
            self.assertEqual(selected_calculations_for_report(run, report), [])
            # 冻结旧格式只验证重新读取，不宣称当前执行通过。
            copied = Path(directory) / "copied-v4"
            for relative in ("research/reports", "research/submissions"):
                shutil.copytree(run / relative, copied / relative)
            gate = json.loads((run / "evidence/gate.json").read_text())
            gate["source_gates"] = [{"role": "BASE_MULTIDIMENSIONAL", "gate_hash": gate["bundle_hash"]}]
            gate["bundle_hash"] = canonical_hash({key: value for key, value in gate.items() if key != "bundle_hash"})
            (copied / "evidence").mkdir()
            (copied / "evidence/gate.json").write_text(json.dumps(gate))
            self.assertEqual(selected_calculations_for_report(copied, report), [])
            source_path = _directory(copied, task["invocation_id"], create=False) / "1.json"
            altered = json.loads(source_path.read_text())
            altered["draft"]["claims"][0]["core_statement"] = "被改写的研究观点。"
            altered["content_hash"] = canonical_hash({key: value for key, value in altered.items() if key != "content_hash"})
            source_path.write_text(json.dumps(altered))
            marker_path = source_path.with_name("accepted.json")
            marker = json.loads(marker_path.read_text())
            marker["submission_content_hash"] = altered["content_hash"]
            marker["marker_hash"] = canonical_hash({key: value for key, value in marker.items() if key != "marker_hash"})
            marker_path.write_text(json.dumps(marker))
            with self.assertRaisesRegex(ValueError, "RELATION_SAVED_MISMATCH"):
                selected_calculations_for_report(copied, report)
            altered["draft"]["claims"][0]["core_statement"] = draft["claims"][0]["core_statement"]
            altered["draft"]["claims"][0]["research_relation_clauses"][0]["research_claim_ref"] = "another_claim"
            altered["content_hash"] = canonical_hash({key: value for key, value in altered.items() if key != "content_hash"})
            source_path.write_text(json.dumps(altered))
            marker["submission_content_hash"] = altered["content_hash"]
            marker["marker_hash"] = canonical_hash({key: value for key, value in marker.items() if key != "marker_hash"})
            marker_path.write_text(json.dumps(marker))
            with self.assertRaisesRegex(ValueError, "RELATION_SAVED_MISMATCH"):
                selected_calculations_for_report(copied, report)

    def test_v4_relation_must_be_on_same_claim_and_one_per_verified_external_ref(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory), version=FORMAL_VERSION)
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            ref = next(iter(packet["reference_map"]["claims"]))
            base = {"claim_id": "ms_valuation_forecast", "question": "供应商估值？",
                    "core_statement": "供应商估值观点。", "research_relation_clauses": [],
                    "kind": "INTERPRETATION", "evidence_refs": [], "research_claim_refs": [ref],
                    "document_refs": [], "assumption_ids": [], "calculation_refs": []}
            second = {**base, "claim_id": "ms_valuation_relation", "research_claim_refs": [],
                      "research_relation_clauses": [], "evidence_refs": ["ev-issuer-body"],
                      "core_statement": "下一条正确解释上游限制。"}
            invalid = {**draft, "claims": [base, second]}
            with self.assertRaisesRegex(ValueError, "RELATION_MISSING:claims\\[0\\]"):
                _assemble_v4_draft(invalid, packet)
            tools = StatelessFixtureTools(default_run_dir=run)
            receipt = self.submit(tools, task, invalid)
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = receipt["final_message"]
            with self.assertRaisesRegex(ValueError, "RESEARCH_SUBMISSION_RELATION_MISSING"):
                read_historical_report_fixture(run, task, receipt["final_message"])
            good = {**base, "research_relation_clauses": [{
                "research_claim_ref": ref, "relation_statement": "上游历史事实不证明供应商公允价值。"}]}
            for defect, claim in (
                ("mixed", {**good, "statement": "另一套正文"}),
                ("duplicate", {**good, "research_relation_clauses": good["research_relation_clauses"] * 2}),
                ("extra", {**good, "research_claim_refs": []}),
                ("unknown", {**good, "research_claim_refs": ["c.unknown"]}),
                ("empty", {**good, "research_relation_clauses": [{"research_claim_ref": ref, "relation_statement": " "}]}),
            ):
                with self.subTest(defect=defect), self.assertRaises(ValueError):
                    _assemble_v4_draft({**draft, "claims": [claim]}, packet)
            with self.assertRaisesRegex(ValueError, "RELATION_REFERENCE_COLLISION"):
                _assemble_v4_draft({**draft, "claims": [{**base, "claim_id": ref,
                    "research_relation_clauses": []}]}, packet)
            full_ref = next(iter(packet["reference_map"]["claims"].values()))["canonical_ref"]
            with self.assertRaisesRegex(ValueError, "RELATION_REFERENCE_COLLISION"):
                _assemble_v4_draft({**draft, "claims": [{**base, "claim_id": full_ref,
                    "research_claim_refs": [full_ref]}]}, packet)
            fixed = {**draft, "claims": [good, second]}
            receipt = self.submit(tools, task, fixed)
            payload["last_assistant_message"] = receipt["final_message"]
            report, _, _ = store_historical_report_fixture(run, task, receipt["final_message"])
            self.assertEqual(report["claims"][1]["statement"], second["core_statement"])
            self.assertEqual(selected_calculations_for_report(run, report), [])

    def test_v4_each_invalid_historical_version_remains_unreadable(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory), version=FORMAL_VERSION)
            ref = next(iter(build_multidimensional_dispatch_packet(
                fixtures.ROOT, run, task["task_name"])["reference_map"]["claims"]))
            draft["claims"] = [{
                "claim_id": "ms_valuation_forecast", "question": "供应商估值？",
                "core_statement": "供应商估值观点。", "research_relation_clauses": [],
                "kind": "INTERPRETATION", "evidence_refs": [], "research_claim_refs": [ref],
                "document_refs": [], "assumption_ids": [], "calculation_refs": [],
            }]
            tools = StatelessFixtureTools(default_run_dir=run)
            for attempt in (1, 2):
                receipt = self.submit(tools, task, draft)
                payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
                payload["last_assistant_message"] = receipt["final_message"]
                with self.assertRaisesRegex(ValueError, "RESEARCH_SUBMISSION_RELATION_MISSING"):
                    read_historical_report_fixture(run, task, receipt["final_message"], attempt=attempt)
            self.assertFalse(list((run / "research/reports").glob("*/dimension-report.json"))[1:])

    def test_v4_multiple_external_refs_and_internal_ref_have_distinct_rules(self):
        from product.runtime.multidimensional_references import build_reference_map
        with tempfile.TemporaryDirectory() as directory:
            _, run, task, _, draft = self.submit_and_start(Path(directory), version=FORMAL_VERSION)
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            dependency = packet["dependency_reports"][0]
            another = {**dependency["claims"][0], "claim_id": "another_verified_upstream_claim"}
            dependency["claims"].append(another)
            gate = json.loads((run / "evidence/gate.json").read_text())
            packet["reference_map"] = build_reference_map(packet, canonical_hash(gate), str(run))
            refs = list(packet["reference_map"]["claims"])
            self.assertEqual(len(refs), 2)
            claim = {"claim_id": "local", "question": "两条上游结论？", "core_statement": "本段观点。",
                     "research_relation_clauses": [
                         {"research_claim_ref": refs[1], "relation_statement": "第二条仅提供期间背景。"},
                         {"research_claim_ref": refs[0], "relation_statement": "第一条限定盈利持续性。"},
                     ], "kind": "INTERPRETATION", "evidence_refs": [],
                     "research_claim_refs": [refs[0], refs[1]], "document_refs": [],
                     "assumption_ids": [], "calculation_refs": []}
            local = {**claim, "claim_id": "local_followup", "core_statement": "内部主张延续前段。",
                     "research_claim_refs": ["local"], "research_relation_clauses": []}
            assembled, _ = _assemble_v4_draft({**draft, "claims": [claim, local]}, packet)
            self.assertEqual(assembled["claims"][0]["statement"],
                             "本段观点。 第二条仅提供期间背景。 第一条限定盈利持续性。")
            self.assertEqual(assembled["claims"][1]["statement"], "内部主张延续前段。")
            self.assertEqual(assembled["claims"][1]["research_claim_refs"], ["local"])
            with self.assertRaisesRegex(ValueError, "RELATION_MISSING"):
                _assemble_v4_draft({**draft, "claims": [{**claim,
                    "research_relation_clauses": claim["research_relation_clauses"][:1]}]}, packet)
            with self.assertRaisesRegex(ValueError, "RELATION_DUPLICATE"):
                _assemble_v4_draft({**draft, "claims": [{**claim,
                    "research_relation_clauses": claim["research_relation_clauses"] * 2}]}, packet)

    def test_stdio_tool_delivery_and_stop_serializes_without_content_change(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory), version=BOUNDED_REVISION_VERSION)
            draft = self.native_draft(draft)
            tools = StatelessFixtureTools(default_run_dir=run)
            draft["claims"] = [{
                "claim_id": "local", "question": "原文如何保留？",
                "core_statement": '模拟原文含"引号"、换行\n与反斜线\\，不改观点。',
                "research_relation_clauses": [],
                "kind": "INTERPRETATION", "evidence_refs": ["ev-issuer-body"],
                "research_claim_refs": [], "document_refs": [], "assumption_ids": [],
            }]
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            draft["claims"][0]["evidence_refs"] = [next(
                ref for ref, original in packet["reference_map"]["evidence"].items() if original == "ev-issuer-body")]
            for serializer in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
                self.assertEqual(json.loads(serializer(packet))["submission_contract"]["tool"], "research_report_submit")
            requests = [
                {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "research_report_submit", "arguments": {"invocation_id": task["invocation_id"], "draft": draft,
                    "submission_token": self.token(run, task)}}},
            ]
            stdout = io.StringIO()
            with patch("sys.stdin", io.StringIO('\n'.join(json.dumps(x) for x in requests))), patch("sys.stdout", stdout):
                self.assertEqual(serve_stdio(tools_override=tools), 0)
            responses = [json.loads(x) for x in stdout.getvalue().splitlines()]
            self.assertIn("research_report_submit", [x["name"] for x in responses[0]["result"]["tools"]])
            receipt = responses[1]["result"]["structuredContent"]
            self.assertEqual(receipt["status"], "DRAFT_STORED_NOT_VALIDATED")
            self.assertEqual(len(list((run / "research/reports").glob('*/dimension-report.json'))), 1)
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = receipt["final_message"]
            record, _ = handle_hook_event(payload, environ=env)
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            report = json.loads((run / record["output_capture"]["path"]).read_text())
            for key, value in draft.items():
                if key in {"claims", "document_selections", "calculation_selections"}:
                    continue
                self.assertEqual(report[key], value)
            self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["core_statement"])
            self.assertEqual(report["claims"][0]["evidence_refs"], ["ev-issuer-body"])
            self.assertEqual(report["run_id"], task["run_id"])
            self.assertEqual((run / record["output_capture"]["raw_path"]).read_text(),
                             receipt["final_message"] + "\n")
            self.assertNotIn(self.token(run, task), stdout.getvalue())
            self.assertNotIn(self.token(run, task), (run / "events/mcp/events.jsonl").read_text())

    def test_historical_state_versions_are_validated_without_rewriting_original(self):
        for corrected in (True, False):
            with self.subTest(corrected=corrected), tempfile.TemporaryDirectory() as directory:
                f, run, task, env, draft = self.submit_and_start(Path(directory))
                tools = StatelessFixtureTools(default_run_dir=run)
                draft["status"] = "SOURCE_LIMITED"
                first = self.submit(tools, task, draft)
                path = _directory(run, task["invocation_id"]) / "1.json"
                original = path.read_bytes()
                payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
                payload["last_assistant_message"] = first["final_message"]
                with self.assertRaisesRegex(ValueError, "SOURCE_LIMITED_STATE_INVALID"):
                    read_historical_report_fixture(run, task, first["final_message"])
                if corrected:
                    draft["evaluation_status"] = "SOURCE_LIMITED"
                second = self.submit(tools, task, draft)
                payload["last_assistant_message"] = second["final_message"]
                if corrected:
                    report, _, _, _ = read_historical_report_fixture(run, task, second["final_message"], attempt=2)
                    self.assertEqual(report["status"], "SOURCE_LIMITED")
                else:
                    with self.assertRaisesRegex(ValueError, "SOURCE_LIMITED_STATE_INVALID"):
                        read_historical_report_fixture(run, task, second["final_message"], attempt=2)
                self.assertEqual(path.read_bytes(), original)
                with self.assertRaisesRegex(ValueError, "LIMIT_EXHAUSTED"):
                    self.submit(tools, task, draft)

    def test_historical_artifact_and_monetary_failures_remain_unreadable(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory))
            tools = StatelessFixtureTools(default_run_dir=run)
            finding = {
                "code": "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED",
                "path": "claims[0].statement", "identifier": "e.short.1",
                "amount_index": 0, "source_unit": "亿美元", "reported_unit": "billion USD",
            }
            draft["artifact_refs"] = ["unapproved-artifact"]
            first = self.submit(tools, task, draft)
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = first["final_message"]
            with patch("product.runtime.codex_hook_recorder._research_report_monetary_findings",
                       return_value=[finding]):
                with self.assertRaisesRegex(ValueError, "MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID"):
                    read_historical_report_fixture(run, task, first["final_message"])
            draft["artifact_refs"] = task["allowed_artifact_refs"][:1]
            second = self.submit(tools, task, draft)
            payload["last_assistant_message"] = second["final_message"]
            with patch("product.runtime.codex_hook_recorder._research_report_monetary_findings",
                       return_value=[finding]):
                with self.assertRaisesRegex(ValueError, finding["code"]):
                    read_historical_report_fixture(run, task, second["final_message"], attempt=2)

    def test_identity_size_scope_path_and_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task, env, draft = self.submit_and_start(Path(directory))
            tools = StatelessFixtureTools(default_run_dir=run)
            for invalid in ({**draft, "run_id": task["run_id"]}, {**draft, "agent": task["agent"]}):
                with self.assertRaisesRegex(ValueError, "IDENTITY_FORBIDDEN"):
                    self.submit(tools, task, invalid)
            with self.assertRaisesRegex(ValueError, "TOO_LARGE"):
                self.submit(tools, task, {"summary": "中" * 90000})
            index = json.loads((run / "research/dispatch-index.json").read_text())
            other = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
            with self.assertRaisesRegex(ValueError, "NOT_ENABLED"):
                tools.research_report_submit(invocation_id=other["invocation_id"], draft=draft)
            receipt = self.submit(tools, task, draft)
            path = _directory(run, task["invocation_id"]) / "1.json"
            value = json.loads(path.read_text()); value["draft"]["summary"] = "tampered"
            path.write_text(json.dumps(value))
            payload = f.stop_payload(task, {}, parent="dependency-parent", child="r")
            payload["last_assistant_message"] = receipt["final_message"]
            with self.assertRaisesRegex(ValueError, "RESEARCH_SUBMISSION_BINDING_INVALID"):
                read_historical_report_fixture(run, task, receipt["final_message"])
        with tempfile.TemporaryDirectory() as directory:
            _, run, task = self.prepare(Path(directory), enabled=False)
            tools = StatelessFixtureTools(default_run_dir=run)
            self.assertNotIn("research_report_submit", [x["name"] for x in tools.available_tools()])
            with self.assertRaisesRegex(ValueError, "NOT_ENABLED"):
                tools.research_report_submit(invocation_id=task["invocation_id"], draft={})
