from __future__ import annotations

import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tests import test_multidimensional_stage as fixtures
from product.council.multidimensional_research import (
    validate_research_dimension_report, finalize_research_dimension_report,
)
from product.runtime.fixture_mcp import StatelessFixtureTools, _write_event
from product.runtime.multidimensional_references import translate_references
from product.runtime.multidimensional_stage import build_multidimensional_dispatch_packet, _text_locator
from product.runtime.multidimensional_stage import (
    serialize_multidimensional_model_context, serialize_multidimensional_initial_context,
    _verified_retry_dependencies, read_retry_dependencies,
)


class ReferenceBoundaryTests(unittest.TestCase):


    def write_historical_dependency_fixture(self, run, task):
        """单独提供旧复用reader需要的向量；不由业务保存隐式生成。"""
        index = json.loads((run / "research/dispatch-index.json").read_text())
        dependency = next(t for t in index["tasks"] if t["task_id"] in task["depends_on"])
        path = next((run / "research/reports").glob("*/dimension-report.json"))
        report = json.loads(path.read_text())
        events = [
            {"hook_event_name": "SubagentStart", "parent_session_id": "historical-fixture",
             "child_session_id": "historical-child"},
            {"hook_event_name": "SubagentStop", "parent_session_id": "historical-fixture",
             "child_session_id": "historical-child", "output_capture": {
                 "status": "SAVED", "task_id": dependency["task_id"],
                 "path": str(path.relative_to(run)), "output_hash": fixtures.canonical_hash(report),
             }},
        ]
        log = run / "invocation/subagent-events.jsonl"
        with log.open('x') as stream:
            stream.write("".join(json.dumps({**e, "event_hash": fixtures.canonical_hash(e)}) + "\n" for e in events))

    def test_report_retry_reuses_dependency_without_dispatch_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task = self.prepare_with_document(Path(directory))
            self.write_historical_dependency_fixture(run, task)
            log = run / "invocation/subagent-events.jsonl"
            reused = _verified_retry_dependencies(run, task["task_name"])
            self.assertEqual(len(reused), 1)
            dependency_path = run / reused[0]["report_ref"]
            original = dependency_path.read_bytes()
            attempt = run / "invocation/retries/research/attempt-1"
            attempt.mkdir(parents=True)
            (attempt / "reused-dependencies.json").write_text(json.dumps({
                "target_task_name": task["task_name"], "dependencies": reused,
            }))
            self.assertEqual(read_retry_dependencies(run, attempt, task["task_name"]), reused)
            self.assertEqual(dependency_path.read_bytes(), original)
            dependency_path.write_bytes(original + b"\n")
            with self.assertRaisesRegex(ValueError, "REUSE_CHANGED"):
                read_retry_dependencies(run, attempt, task["task_name"])
            dependency_path.write_bytes(original)
            log = run / "invocation/subagent-events.jsonl"
            original_log = log.read_text()
            log.write_text(original_log.replace('"SAVED"', '"FAILED"'))
            with self.assertRaisesRegex(ValueError, "REUSE_EVENT_INVALID"):
                read_retry_dependencies(run, attempt, task["task_name"])

    def prepare_with_document(self, root):
        original = fixtures.gate_for

        def gate_with_document(handoff):
            gate = original(handoff)
            gate["allowed_evidence"].append({
                "evidence_id": "ev-issuer-body", "security_id": handoff["portfolio"]["positions"][0]["security_id"],
                "semantic_field": "earnings_release", "value": "Issuer verified earnings discussion. " * 30,
                "source_id": "sec-filing:test", "source_type": "sec",
                "source_locator": "https://www.sec.gov/Archives/example.htm",
                "as_of": "2026-09-10T20:00:00Z", "published_at": "2026-09-10T20:00:00Z",
                "retrieved_at": "2026-09-11T11:00:00Z", "raw_content_hash": "a" * 64,
                "section": "earnings_release", "metadata": {"description": "Issuer earnings release"},
            })
            gate["allowed_evidence_ids"] = sorted(x["evidence_id"] for x in gate["allowed_evidence"])
            gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
            gate["bundle_hash"] = fixtures.canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
            return gate

        f = fixtures.MultidimensionalStageTests()
        with patch.object(fixtures, "gate_for", gate_with_document):
            run, _ = f.prepare(root, count=1)
        index = json.loads((run / "research/dispatch-index.json").read_text())
        f.save_fundamental_dependency(run, index)
        # 显式历史读取向量；不是当前宿主进程结果。
        (run / "invocation").mkdir(exist_ok=True)
        (run / "invocation/process-result.json").write_text(json.dumps({
            "source_integrity_unchanged": True, "timed_out": False, "process_exit_code": 0,
        }))
        task = next(x for x in index["tasks"] if x["capability"] == "RESEARCH_REPORT")
        return f, run, task

    def test_contract_rules_delivered_without_changing_frozen_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, task = self.prepare_with_document(Path(directory))
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            frozen = copy.deepcopy(packet)
            for serialize in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
                context = json.loads(serialize(packet))
                self.assertIn("evaluation_status 必须为 SOURCE_LIMITED", context["output_contract_rules"]["status"])
                self.assertEqual(context["task"]["allowed_documents"], translate_references(
                    {"documents": task["allowed_documents"]}, packet["reference_map"], to_model=True,
                )["documents"])
                self.assertIn("不得重写", context["output_contract_rules"]["documents"])
            self.assertEqual(packet, frozen)

    def test_attribution_guidance_delivered_only_to_research_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, task = self.prepare_with_document(Path(directory))
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            frozen = copy.deepcopy(packet)
            # Verify the same task locks the actual, aligned Skill, not only
            # dynamically injected guidance. This proves the configured binding,
            # not runtime loading or semantic quality of a generated report.
            import hashlib
            skill_path = fixtures.ROOT / "product/skills/research-report-analysis/SKILL.md"
            index = json.loads((run / "research/dispatch-index.json").read_text())
            indexed = next(t for t in index["tasks"] if t["task_name"] == task["task_name"])
            invocation = json.loads((run / indexed["invocation_path"]).read_text())
            self.assertEqual(invocation["skill"]["version"], "1.4.2")
            self.assertEqual(invocation["skill"]["content_hash"], hashlib.sha256(skill_path.read_bytes()).hexdigest())
            agent_path = fixtures.ROOT / "product/.codex/agents/runtime_company_analyst.toml"
            self.assertEqual(invocation["agent_binding"]["content_hash"], hashlib.sha256(agent_path.read_bytes()).hexdigest())
            # 角色只绑定方法 Skill；当前草稿/归属规则来自实际任务契约。
            # 配置和交付一致性不冒充真实 Skill 加载或研究语义质量。
            import tomllib
            config = tomllib.loads(agent_path.read_text())
            self.assertEqual(config["sandbox_mode"], "read-only")
            self.assertTrue(any(entry["enabled"] and entry["path"] == "skills/research-report-analysis"
                                for entry in config["skills"]["config"]))
            for serialize in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
                context = json.loads(serialize(packet))
                guide = context["research_attribution_guidance"]
                from product.runtime.multidimensional_stage import RESEARCH_ATTRIBUTION_GUIDANCE
                self.assertEqual(guide, RESEARCH_ATTRIBUTION_GUIDANCE)
                self.assertEqual(guide["version"], "research-report-attribution/1.3.1")
                self.assertIn("独立陈述供应商观点可只引许可 Evidence", guide["source"])
                self.assertIn("最后填写引用", guide["self_check"])
                self.assertIn("完全没有估值观点", guide["upstream_scope"])
                for field in ("evidence_refs", "document_refs", "research_claim_refs"):
                    self.assertIn(field, guide["self_check"])
                self.assertIn("不要求覆盖全部上游", guide["self_check"])
                self.assertIn("claims[].evidence_refs", guide["source"])
                self.assertIn("research_claim_refs", guide["source"])
                self.assertIn("research_relationships 可以为空", guide["source"])
                self.assertIn("不得借用 SEC/发行人 document_id", guide["source"])
                self.assertIn("不等于完全没有估值信息", guide["upstream_scope"])
                self.assertIn("不自动推翻上游缺口", guide["upstream_scope"])
                self.assertIn("ID 合法不代表语义支持已验证", guide["self_check"])
                self.assertIn("每一个 resulting_claim_ref", guide["self_check"])
                self.assertIn("收购事实不支持独立研报覆盖不足", guide["self_check"])
            self.assertEqual(packet, frozen)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            for other in index["tasks"]:
                if other["capability"] == "RESEARCH_REPORT":
                    continue
                other_packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, other["task_name"])
                self.assertNotIn("research_attribution_guidance", json.loads(serialize_multidimensional_model_context(other_packet)))
                if other["capability"] == "FUNDAMENTAL_EVENT":
                    self.assertNotIn("research_attribution_guidance", json.loads(serialize_multidimensional_initial_context(other_packet)))

    def test_evidence_only_and_issuer_document_relationship_remain_valid(self):
        # Synthetic contract checks, not a claim that either wording is LLM-verified.
        for with_document in (False, True):
            with self.subTest(with_document=with_document), tempfile.TemporaryDirectory() as directory:
                f, run, task = self.prepare_with_document(Path(directory))
                packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                upstream = next(iter(packet["reference_map"]["claims"]))
                draft = f.dimension_draft(task)
                document = task["allowed_documents"][0]
                document_ref = next(ref for ref, full in packet["reference_map"]["documents"].items()
                                    if full == document["document_id"])
                draft["claims"] = [{
                    "claim_id": "comparison", "question": "与上游何种关系？",
                    "statement": "模拟：披露为上游经营分析补充依据，不推翻其限定缺口。",
                    "kind": "COMPARISON", "evidence_refs": ["ev-issuer-body"],
                    "research_claim_refs": [upstream],
                    "document_refs": [document["document_id"]] if with_document else [],
                    "assumption_ids": [],
                }]
                if with_document:
                    draft["document_selections"] = [document_ref]
                    draft["research_relationships"] = [{
                        "relationship_id": "issuer-support", "document_id": document["document_id"],
                        "target_claim_refs": [upstream], "effect": "SUPPORT",
                        "rationale": "模拟：该发行人披露自身提供经营依据。",
                        "resulting_claim_refs": ["comparison"],
                    }]
                original = copy.deepcopy(draft)
                report, _, _ = f.read_dimension_draft(run, task, draft)
                self.assertEqual(draft, original)
                self.assertFalse((run / "invocation/subagent-events.jsonl").exists())
                self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["statement"])
                self.assertEqual(len(report["research_relationships"]), int(with_document))

    def test_metadata_and_state_fail_closed_without_mutating_or_publishing(self):
        for defect, code in (("state", "SOURCE_LIMITED_STATE_INVALID"),
                             ("document", r"SCHEMA_ENUM_INVALID:\$\.document_selections\[0\]"),
                             ("failed_evaluation", "FAILED_EVALUATION_INVALID")):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                f, run, task = self.prepare_with_document(Path(directory))
                draft = f.dimension_draft(task)
                if defect == "document":
                    draft["document_selections"] = ["d.not-authorized.1"]
                else:
                    draft["status"] = "SOURCE_LIMITED" if defect == "state" else "FAILED"
                    draft["evaluation_status"] = "NOT_EVALUATED" if defect == "state" else "PASS"
                original = copy.deepcopy(draft)
                with self.assertRaisesRegex(ValueError, code):
                    f.read_dimension_draft(run, task, draft)
                self.assertEqual(draft, original)
                corrected = copy.deepcopy(draft)
                if defect == "document":
                    packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                    corrected["document_selections"] = list(packet["reference_map"]["documents"])
                else:
                    corrected["evaluation_status"] = "SOURCE_LIMITED" if defect == "state" else "FAIL"
                report, _, _ = f.read_dimension_draft(run, task, corrected)
                self.assertEqual(report["evaluation_status"], corrected["evaluation_status"])
                self.assertFalse((run / "invocation/subagent-events.jsonl").exists())

    def test_formal_document_metadata_and_frozen_packet_drift_remain_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task = self.prepare_with_document(Path(directory))
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            draft = f.dimension_draft(task)
            draft["document_selections"] = list(packet["reference_map"]["documents"])
            report, _, _ = f.read_dimension_draft(run, task, draft)
            self.assertTrue(report["documents"])
            for defect, code in (("metadata", "DOCUMENT_METADATA_DRIFT"), ("foreign", "DOCUMENT_NOT_ALLOWED")):
                changed = copy.deepcopy(report)
                if defect == "metadata": changed["documents"][0]["as_of"] = "2026-09-11T20:00:00Z"
                else: changed["documents"][0]["document_id"] = "foreign-document"
                changed = finalize_research_dimension_report(changed)
                original = copy.deepcopy(changed)
                with self.subTest(defect=defect), self.assertRaisesRegex(ValueError, code):
                    validate_research_dimension_report(
                        changed, expected_bindings=report["bindings"],
                        allowed_security_ids=task["security_ids"],
                        allowed_evidence_ids=task["allowed_evidence_ids"],
                        allowed_documents=task["allowed_documents"],
                    )
                self.assertEqual(changed, original)
            path = run / task["packet_path"]
            frozen = json.loads(path.read_text())
            frozen["instruction"] = "tampered"
            path.write_text(json.dumps(frozen))
            with self.assertRaisesRegex(ValueError, "PACKET_HASH_MISMATCH"):
                f.read_dimension_draft(run, task, draft)

    def test_short_query_calculate_and_read_preserve_canonical_report(self):
        f = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = f.prepare(Path(directory), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            mapping = packet["reference_map"]
            short, full = next(iter(mapping["evidence"].items()))
            args = {"run_id": task["run_id"], "agent": task["agent"], "invocation_id": task["invocation_id"]}
            tools = StatelessFixtureTools(default_run_dir=run)
            result = tools.query(**args, evidence_ids=[short])
            self.assertEqual(result["evidence"][0]["evidence_id"], short)
            self.assertEqual(tools.events[-1]["evidence_ids"], [full])
            self.assertEqual(result["reference_map_hash"], mapping["map_hash"])
            short_ids = list(mapping["evidence"])[:2]
            calculated = tools.calculate(**args, evidence_ids=short_ids, calculation_id="ratio-test", operation="ratio")
            _write_event(run / "events/mcp/events.jsonl", tools.events[-1])
            self.assertEqual(calculated["evidence_ids"], short_ids)
            ledger = json.loads((run / calculated["artifact_ref"]).read_text().splitlines()[0])
            self.assertEqual(ledger["evidence_ids"], [mapping["evidence"][s] for s in short_ids])
            self.assertEqual(ledger["output"]["value"], calculated["value"])
            with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
                tools.query(**args, evidence_ids=["e.other-task.1"])
            draft = f.dimension_draft(task)
            draft["claims"] = [{
                "claim_id": "local-1", "question": "事实？", "statement": f"模拟文本保留 {short}",
                "kind": "FACT", "evidence_refs": [short], "research_claim_refs": [],
                "document_refs": [], "assumption_ids": [],
            }]
            original = copy.deepcopy(draft)
            report, _, _ = f.read_dimension_draft(run, task, draft)
            self.assertEqual(report["claims"][0]["evidence_refs"], [full])
            self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["statement"])
            self.assertEqual(draft, original)
            self.assertFalse((run / "invocation/subagent-events.jsonl").exists())
            broken = copy.deepcopy(mapping)
            broken["evidence"][short] = "ev-forged"
            with self.assertRaisesRegex(ValueError, "MAP_INVALID"):
                translate_references(draft, broken)

    def test_legacy_packet_keeps_full_id_tool_protocol(self):
        f = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = f.prepare(Path(directory), count=1)
            index_path = run / "research/dispatch-index.json"
            index = json.loads(index_path.read_text())
            task = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
            path = run / task["packet_path"]
            packet = json.loads(path.read_text())
            packet.pop("reference_transport_version")
            path.write_text(json.dumps(packet))
            task["packet_hash"] = fixtures.canonical_hash(packet)
            index_path.write_text(json.dumps(index))
            built = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            self.assertNotIn("reference_map", built)
            full = task["allowed_evidence_ids"][0]
            output = StatelessFixtureTools(default_run_dir=run).query(
                run_id=task["run_id"], agent=task["agent"], invocation_id=task["invocation_id"], evidence_ids=[full])
            self.assertEqual(output["evidence"][0]["evidence_id"], full)

    def test_upstream_claim_and_reference_type_remain_exact_without_auto_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            f, run, task = self.prepare_with_document(Path(directory))
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            mapping = packet["reference_map"]
            claim_short = next(iter(mapping["claims"]))
            draft = f.dimension_draft(task)
            draft["claims"] = [{
                "claim_id": "local", "question": "对照？", "statement": "模拟研究主张关系。",
                "kind": "INTERPRETATION", "evidence_refs": [],
                "research_claim_refs": ["mrvl_growth_continuity"],
                "document_refs": [], "assumption_ids": [],
            }]
            original = copy.deepcopy(draft)
            with self.assertRaisesRegex(ValueError, "RESEARCH_CLAIM_DANGLING"):
                f.read_dimension_draft(run, task, draft)
            self.assertEqual(draft, original)
            draft["claims"][0]["research_claim_refs"] = [claim_short]
            report, _, _ = f.read_dimension_draft(run, task, draft)
            self.assertEqual(report["claims"][0]["research_claim_refs"],
                             [mapping["claims"][claim_short]["canonical_ref"]])
            with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
                translate_references({"evidence_refs": [claim_short]}, mapping)
            draft["claims"][0]["evidence_refs"] = ["e.wrong.1"]
            with self.assertRaisesRegex(ValueError, "REFERENCE_UNKNOWN"):
                f.read_dimension_draft(run, task, draft)
            self.assertFalse((run / "invocation/subagent-events.jsonl").exists())

    def test_heading_not_confused_with_short_substantive_text(self):
        heading = {"value": "Item 1. Business 3 ", "metadata": {"section": "business", "truncated": False}}
        self.assertEqual(_text_locator(heading)["content_kind"], "HEADING_ONLY")
        body = {"value": "We sell chips.", "metadata": {"section": "business", "truncated": False}}
        self.assertEqual(_text_locator(body)["content_kind"], "SECTION_TEXT")
        self.assertEqual(_text_locator({"value": "We sell chips."})["content_kind"], "UNKNOWN")
        self.assertEqual(_text_locator({"value": "We sell chips.", "metadata": {"section": "business", "truncated": True}})["content_kind"], "SECTION_EXCERPT")
