"""普通股/资料准备的显式局部补丁与完整业务重验；不签发宿主修订权限。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash
from product.tools.revision import _apply
from tests import test_common_stock_semantic_handoff as company_fixtures
from tests import test_material_semantic_handoff as material_fixtures
from tests.test_research_materials_stage import FakeOpenAlexClient


class ResearchLocalRevisionHandoffTests(unittest.TestCase):
    def prepare_period_case(self, root, *, single=True):
        from product.runtime import common_stock_stage as stage
        from tests import test_common_stock_research_contracts as fixtures
        from tests.test_single_stock_input import SingleStockCompanyTests
        if single:
            source, _, gate, _ = SingleStockCompanyTests().prepare_values()
            second = copy.deepcopy(gate["allowed_evidence"][0])
            second.update(evidence_id="ev-alb-cash", semantic_field="operating_cash_flow", value="20")
            gate["allowed_evidence"].append(second)
            gate["input_evidence_ids"].append(second["evidence_id"])
            gate["allowed_evidence_ids"].append(second["evidence_id"])
            input_args = {"research_input_path": root / "input.json"}
        else:
            source = fixtures.stock_handoff(1)
            gate = fixtures.gate_for(source, "period-holding-run")
            input_args = {"handoff_path": root / "input.json"}
        for fact, start in zip(gate["allowed_evidence"], ("2026-04-01", "2026-01-01"), strict=True):
            fact["metadata"] = {"context_type": "duration", "period_start": start, "period_end": "2026-06-30"}
        gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
        (root / "input.json").write_text(json.dumps(source))
        (root / "gate.json").write_text(json.dumps(gate))
        run = root / "run"
        stage.prepare_common_stock_stage_run(fixtures.ROOT, **input_args,
            gate_path=root / "gate.json", run_dir=run, run_id=gate["run_id"], model="gpt-5.6-terra")
        task = json.loads((run / "research/dispatch-index.json").read_text())["tasks"][0]
        request = json.loads((run / task["request_path"]).read_text())
        helper = company_fixtures.CommonStockSemanticHandoffTests()
        packet = helper.frozen_packet(run, task)
        helper.call(run, request, "query", evidence_ids=list(packet["reference_map"]["evidence"]))
        draft = helper.draft(request, packet)
        draft["claims"][0].update(kind="FACT", evidence_refs=list(packet["reference_map"]["evidence"]),
            statement="季度2026年4月1日至6月30日、累计2026年1月1日至6月30日；期间不可混同。")
        return run, task, draft

    def test_explicit_period_patch_passes_full_persistence_without_changing_base(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run, task, draft = self.prepare_period_case(root)
            helper = company_fixtures.CommonStockSemanticHandoffTests()
            gate_before = (run / "evidence/gate.json").read_bytes()
            original = copy.deepcopy(draft)
            base = root / "authored.json"
            base.write_text(json.dumps(draft, ensure_ascii=False))
            before = base.read_bytes()
            with self.assertRaisesRegex(ValueError, "EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE:claim-core:2026-06-30"):
                helper.read_report(run, task, draft)
            statement = "季度2026-04-01至2026-06-30、累计2026-01-01至2026-06-30；期间不可混同。"
            # 纯补丁算法向量；作用域由测试给定，不表示服务端已签发修订授权。
            repaired = _apply(draft, [{"op": "replace", "path": "/claims/0/statement", "value": statement}], ["/claims/0/statement"])
            report, output = helper.save_report(run, task, repaired)
            self.assertEqual(report["claims"][0]["statement"], statement)
            for field in ("kind", "assumption_ids", "counter_claim_refs", "invalidation_condition_ids"):
                self.assertEqual(report["claims"][0][field], draft["claims"][0][field])
            self.assertEqual(report["status"], draft["status"])
            self.assertTrue(Path(output["markdown"]).is_file())
            self.assertEqual(base.read_bytes(), before)
            self.assertEqual(draft, original)
            self.assertEqual((run / "evidence/gate.json").read_bytes(), gate_before)
            helper.assert_no_execution(run)

    def test_period_patch_scope_cannot_change_refs_kind_status_identity_or_other_claim(self):
        cases = [("/claims/0/kind", "INTERPRETATION"), ("/claims/0/evidence_refs", []),
                 ("/status", "LOW_CONFIDENCE"), ("/claims/1/statement", "其他主张"), ("/run_id", "other-run")]
        with tempfile.TemporaryDirectory() as directory:
            run, task, draft = self.prepare_period_case(Path(directory))
            original = copy.deepcopy(draft)
            for path, value in cases:
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, "LOCAL_REVISION_PATH_FORBIDDEN" if path == "/run_id" else "LOCAL_REVISION_OUT_OF_SCOPE"):
                    _apply(draft, [{"op": "replace", "path": path, "value": value}], ["/claims/0/statement"])
            repaired = _apply(draft, [{"op": "replace", "path": "/claims/0/statement", "value": "仍没有完整期间。"}], ["/claims/0/statement"])
            with self.assertRaisesRegex(ValueError, "PERIOD_LINEAGE_INCOMPLETE"):
                company_fixtures.CommonStockSemanticHandoffTests().read_report(run, task, repaired)
            self.assertEqual(draft, original)
            self.assertFalse((run / "research/reports").exists())

    def test_retired_stop_does_not_grant_revision_to_legacy_or_unbound_task(self):
        for single in (False, True):
            with self.subTest(single=single), tempfile.TemporaryDirectory() as directory:
                run, _, draft = self.prepare_period_case(Path(directory), single=single)
                before = {path: path.read_bytes() for path in run.rglob("*") if path.is_file()}
                with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                    handle_hook_event({"hook_event_name": "SubagentStop", "model": "foreign-model",
                                       "last_assistant_message": json.dumps(draft)}, environ={"STOCK_AGENT_RUN_DIR": str(run)})
                self.assertEqual({path: path.read_bytes() for path in run.rglob("*") if path.is_file()}, before)
                self.assertFalse((run / "research/raw-drafts").exists())

    def prepare(self, root, role):
        if role == "company":
            helper = company_fixtures.CommonStockSemanticHandoffTests()
            run, task, request, view = helper.prepare(str(root))
            helper.call(run, request, "query", evidence_ids=view["allowed_evidence_ids"])
            helper.call(run, request, "calculate", evidence_ids=list(reversed(view["allowed_evidence_ids"])), operation="ratio")
            draft = helper.draft(request, helper.frozen_packet(run, task))
        else:
            helper = material_fixtures.MaterialSemanticHandoffTests()
            run, task, _ = helper.prepare(root)
            helper.search(run, task)
            helper.fetch(run, task)
            draft = helper.draft()
        return run, task, draft

    def read_business(self, role, run, task, draft):
        if role == "company":
            return company_fixtures.CommonStockSemanticHandoffTests().read_report(run, task, draft)[0]
        return material_fixtures.stage.assemble_material_semantic_draft(draft, task=task, run_dir=run)[0]

    def test_schema_patch_preserves_base_and_all_other_research_fields(self):
        for role in ("company", "materials"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
            ):
                run, task, valid = self.prepare(Path(directory), role)
                invalid = copy.deepcopy(valid)
                field = "research_summary" if role == "company" else "summary"
                summary = invalid.pop(field)
                original = copy.deepcopy(invalid)
                with self.assertRaisesRegex(ValueError, "SCHEMA_REQUIRED_MISSING"):
                    self.read_business(role, run, task, invalid)
                repaired = _apply(invalid, [{"op": "add", "path": "/" + field, "value": summary}], ["/" + field])
                self.assertEqual(repaired, valid)
                report = self.read_business(role, run, task, repaired)
                self.assertEqual(report[field], summary)
                self.assertEqual(invalid, original)
                self.assertFalse((run / "invocation").exists())
                self.assertFalse((run / "research/raw-drafts").exists())

    def test_local_patch_cannot_insert_model_identity_or_expand_allowed_fields(self):
        for role in ("company", "materials"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
            ):
                run, task, draft = self.prepare(Path(directory), role)
                field = "research_summary" if role == "company" else "summary"
                original = copy.deepcopy(draft)
                for path, value in (("/status", "SOURCE_LIMITED"), ("/model", "foreign-model"), ("/run_id", "other")):
                    with self.subTest(path=path), self.assertRaisesRegex(ValueError, "LOCAL_REVISION_PATH_FORBIDDEN" if path == "/run_id" else "LOCAL_REVISION_OUT_OF_SCOPE"):
                        _apply(draft, [{"op": "add", "path": path, "value": value}], ["/" + field])
                with self.assertRaisesRegex(ValueError, "SCHEMA_EXTRA_PROPERTY"):
                    self.read_business(role, run, task, {**draft, "model": "foreign-model"})
                self.assertEqual(draft, original)
                self.assertFalse((run / "research/raw-drafts").exists())

    def test_unknown_reference_requires_explicit_choice_and_full_revalidation(self):
        for still_wrong in (False, True):
            with self.subTest(still_wrong=still_wrong), tempfile.TemporaryDirectory() as directory:
                run, task, draft = self.prepare(Path(directory), "company")
                original_claim = copy.deepcopy(draft["claims"][0])
                draft["claims"][0]["evidence_refs"] = ["e.unknown"]
                before = copy.deepcopy(draft)
                with self.assertRaisesRegex(ValueError, "SCHEMA_ENUM_INVALID"):
                    self.read_business("company", run, task, draft)
                claim = {**original_claim, "evidence_refs": ["e.still-unknown"]} if still_wrong else original_claim
                repaired = _apply(draft, [{"op": "replace", "path": "/claims/0", "value": claim}], ["/claims/0"])
                if still_wrong:
                    with self.assertRaisesRegex(ValueError, "SCHEMA_ENUM_INVALID"):
                        self.read_business("company", run, task, repaired)
                else:
                    report = self.read_business("company", run, task, repaired)
                    self.assertEqual(report["claims"][0]["statement"], original_claim["statement"])
                self.assertEqual(draft, before)
                self.assertFalse((run / "research/reports").exists())

    def test_material_document_selection_requires_explicit_correction(self):
        for still_wrong in (False, True):
            with self.subTest(still_wrong=still_wrong), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
            ):
                run, task, draft = self.prepare(Path(directory), "materials")
                original = copy.deepcopy(draft["selections"][0])
                draft["selections"][0]["document_id"] = "nonexistent-document"
                before = copy.deepcopy(draft)
                with self.assertRaisesRegex(ValueError, "DOCUMENT_SELECTION_INVALID"):
                    self.read_business("materials", run, task, draft)
                selection = {**original, "document_id": "still-nonexistent"} if still_wrong else original
                repaired = _apply(draft, [{"op": "replace", "path": "/selections/0", "value": selection}], ["/selections/0"])
                if still_wrong:
                    with self.assertRaisesRegex(ValueError, "DOCUMENT_SELECTION_INVALID"):
                        self.read_business("materials", run, task, repaired)
                else:
                    self.assertEqual(self.read_business("materials", run, task, repaired)["selections"], [original])
                self.assertEqual(draft, before)
                self.assertFalse((run / "research/material-results").exists())

    def test_material_integrity_failure_never_creates_report_or_revision_authority(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient
        ):
            run, task, draft = self.prepare(Path(directory), "materials")
            document = next((run / "research/materials").glob("*/document-*.json"))
            document.write_text(document.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "RESEARCH_MATERIALS_ARTIFACT_HASH_MISMATCH"):
                self.read_business("materials", run, task, draft)
            self.assertFalse((run / "research/material-results").exists())
            self.assertFalse((run / "research/raw-drafts").exists())
            self.assertFalse((run / "invocation").exists())


if __name__ == "__main__":
    unittest.main()
