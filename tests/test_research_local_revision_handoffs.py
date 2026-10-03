"""普通股/资料准备的真实 Stop 接缝；模型消息和来源客户端为合成测试输入。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash
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
        helper = fixtures.CommonStockNativeStageTests()
        env = helper.hook_environment(run)
        handle_hook_event(helper.dispatch_payload(run, task), environ=env)
        start = helper.event("SubagentStart", parent="parent-session", child="period-child", turn="period-turn")
        _, response = handle_hook_event(start, environ=env)
        packet = json.loads(response["hookSpecificOutput"]["additionalContext"])
        request = json.loads((run / task["request_path"]).read_text())
        semantic = company_fixtures.CommonStockSemanticHandoffTests()
        semantic.call(run, request, "query", evidence_ids=packet["allowed_evidence_ids"])
        draft = semantic.draft(request, semantic.frozen_packet(run, task))
        draft["claims"][0].update(kind="FACT", evidence_refs=packet["allowed_evidence_ids"],
            statement="季度2026年4月1日至6月30日、累计2026年1月1日至6月30日；期间不可混同。")
        return run, env, start, draft

    def test_single_company_period_statement_patch_passes_full_persistence_without_changing_base(self):
        with tempfile.TemporaryDirectory() as directory:
            run, env, start, draft = self.prepare_period_case(Path(directory))
            gate_before = (run / "evidence/gate.json").read_bytes()
            first, repair = self.first(env, start, draft)
            self.assertEqual(repair["allowed_paths"], ["/claims/0/statement"])
            self.assertEqual(repair["validation_details"]["findings"][0]["missing_dates"], ["2026-06-30"])
            from product.runtime.codex_hook_recorder import _simple_research_repair_packet
            payload = {**start, "last_assistant_message": json.dumps(draft, ensure_ascii=False)}
            for code, attempt in (("EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE:unknown:2026-06-30", 1),
                                  ("EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE:claim-core:2026-01-01", 1),
                                  (repair["validation_error"], 2)):
                self.assertIsNone(_simple_research_repair_packet(payload, first, env,
                    failure_code=code, attempt=attempt))
            base = run / first["output_capture"]["raw_path"]
            before = base.read_bytes()
            statement = "季度2026-04-01至2026-06-30、累计2026-01-01至2026-06-30；期间不可混同。"
            second, _ = self.stop(env, start, {"base_draft_ref": repair["base_draft_ref"], "changes": [
                {"op": "replace", "path": "/claims/0/statement", "value": statement}]})
            self.assertEqual(second["output_capture"]["status"], "SAVED", second)
            saved = json.loads((run / second["output_capture"]["path"]).read_text())
            self.assertEqual(saved["claims"][0]["statement"], statement)
            for field in ("kind", "assumption_ids", "counter_claim_refs", "invalidation_condition_ids"):
                self.assertEqual(saved["claims"][0][field], draft["claims"][0][field])
            self.assertEqual(saved["status"], draft["status"])
            self.assertEqual(base.read_bytes(), before)
            self.assertEqual((run / "evidence/gate.json").read_bytes(), gate_before)

    def test_period_patch_cannot_change_refs_kind_status_identity_other_claim_or_hide_missing_period(self):
        cases = [("/claims/0/kind", "INTERPRETATION"), ("/claims/0/evidence_refs", []),
                 ("/status", "LOW_CONFIDENCE"), ("/claims/1/statement", "其他主张"),
                 ("/run_id", "other-run"), ("/claims/0/statement", "仍没有完整期间。")]
        for path, value in cases:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                run, env, start, draft = self.prepare_period_case(Path(directory))
                _, repair = self.first(env, start, draft)
                second, _ = self.stop(env, start, {"base_draft_ref": repair["base_draft_ref"], "changes": [
                    {"op": "replace", "path": path, "value": value}]})
                self.assertEqual(second["output_capture"]["status"], "FAILED", second)
                self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
                self.assertFalse((run / "research/reports").exists())
                if path == "/claims/0/statement":
                    self.assertIn("PERIOD_LINEAGE_INCOMPLETE", second["output_capture"]["failure_code"])
                else:
                    self.assertIn("LOCAL_REVISION_", second["output_capture"]["failure_code"])
                third, _ = self.stop(env, start, draft)
                self.assertEqual(third["output_capture"]["failure_code"], "LOCAL_REVISION_LIMIT_EXHAUSTED")

    def test_period_revision_does_not_extend_legacy_holding_or_unbound_task(self):
        for single in (False, True):
            with self.subTest(single=single), tempfile.TemporaryDirectory() as directory:
                _, env, start, draft = self.prepare_period_case(Path(directory), single=single)
                record, response = self.stop(env, start, draft, **({"model": "foreign-model"} if single else {}))
                self.assertEqual(record["output_capture"]["repair_state"], "NOT_ALLOWED")
                self.assertNotIn("repair_request", record)
                self.assertEqual(response, {})

    def prepare(self, root, role):
        if role == "company":
            helper = company_fixtures.CommonStockSemanticHandoffTests()
            run, task, request, packet, env, start = helper.prepare(str(root))
            helper.call(run, request, "query", evidence_ids=packet["allowed_evidence_ids"])
            helper.call(run, request, "calculate", evidence_ids=list(reversed(packet["allowed_evidence_ids"])), operation="ratio")
            draft = helper.draft(request, helper.frozen_packet(run, task))
        else:
            helper = material_fixtures.MaterialSemanticHandoffTests()
            run, task, packet, env, start = helper.prepare(root)
            helper.search(run, task)
            helper.fetch(run, task)
            draft = helper.draft()
        return run, env, start, draft

    def stop(self, env, start, draft, **override):
        return handle_hook_event({**start, "hook_event_name": "SubagentStop",
                                 "last_assistant_message": json.dumps(draft, ensure_ascii=False),
                                 **override}, environ=env)

    def first(self, env, start, draft):
        record, response = self.stop(env, start, draft)
        self.assertEqual(record["hook_event_name"], "SubagentStopBlocked", record)
        self.assertEqual(record["output_capture"]["repair_state"], "REPAIR_REQUESTED", record)
        repair = json.loads(response["reason"])
        self.assertNotIn("binding_hash", repair)
        self.assertNotIn("original_draft", repair)
        return record, repair

    def test_schema_patch_preserves_base_and_all_other_research_fields(self):
        for role in ("company", "materials"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient,
            ):
                run, env, start, valid = self.prepare(Path(directory), role)
                invalid = copy.deepcopy(valid)
                field = "research_summary" if role == "company" else "summary"
                original_summary = invalid.pop(field)
                first, repair = self.first(env, start, invalid)
                self.assertEqual(repair["allowed_paths"], ["/" + field])
                base_path = run / first["output_capture"]["raw_path"]
                original = base_path.read_bytes()
                second, response = self.stop(env, start, {
                    "base_draft_ref": repair["base_draft_ref"],
                    "changes": [{"op": "add", "path": "/" + field, "value": original_summary}],
                })
                self.assertEqual(second["output_capture"]["status"], "SAVED", second)
                self.assertEqual(second["output_capture"]["repair_state"], "REPAIRED")
                self.assertEqual(response, {})
                self.assertEqual(base_path.read_bytes(), original)
                self.assertEqual(second["local_revision"]["base_hash"], canonical_hash(invalid))
                saved = json.loads((run / second["output_capture"]["path"]).read_text())
                self.assertEqual(saved[field], original_summary)
                if role == "company":
                    self.assertEqual(second["output_capture"]["semantic_output_hash"], canonical_hash(valid))
                else:
                    for key in ("status", "selections", "gaps"):
                        self.assertEqual(saved[key], valid[key])

    def test_wrong_model_does_not_consume_revision_or_write_an_attempt(self):
        for role in ("company", "materials"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient,
            ):
                run, env, start, draft = self.prepare(Path(directory), role)
                field = "research_summary" if role == "company" else "summary"
                summary = draft.pop(field)
                _, repair = self.first(env, start, draft)
                revision = {"base_draft_ref": repair["base_draft_ref"],
                            "changes": [{"op": "add", "path": "/" + field, "value": summary}]}
                before = {str(path): path.read_bytes() for path in (run / "research/raw-drafts").glob("*")}
                rejected, _ = self.stop(env, start, revision, model="foreign-model")
                self.assertEqual(rejected["output_capture"]["status"], "FAILED")
                self.assertNotEqual(rejected["identity_binding"]["status"], "BOUND")
                self.assertEqual({str(path): path.read_bytes() for path in (run / "research/raw-drafts").glob("*")}, before)
                accepted, _ = self.stop(env, start, revision)
                self.assertEqual(accepted["output_capture"]["attempt"], 2)
                self.assertEqual(accepted["output_capture"]["status"], "SAVED", accepted)

    def test_out_of_scope_second_attempt_exhausts_quota_not_a_new_full_draft(self):
        for role in ("company", "materials"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient,
            ):
                run, env, start, draft = self.prepare(Path(directory), role)
                field = "research_summary" if role == "company" else "summary"
                draft.pop(field)
                _, repair = self.first(env, start, draft)
                second, _ = self.stop(env, start, {
                    "base_draft_ref": repair["base_draft_ref"],
                    "changes": [{"op": "replace", "path": "/status", "value": "SOURCE_LIMITED"}],
                })
                self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED", second)
                self.assertEqual(second["output_capture"]["failure_code"], "LOCAL_REVISION_OUT_OF_SCOPE:/status")
                originals = {str(path): path.read_bytes() for path in (run / "research/raw-drafts").glob("*")}
                third, _ = self.stop(env, start, {**draft, field: "新整稿"})
                self.assertEqual(third["output_capture"]["failure_code"], "LOCAL_REVISION_LIMIT_EXHAUSTED")
                self.assertEqual({str(path): path.read_bytes() for path in (run / "research/raw-drafts").glob("*")}, originals)

    def test_unknown_reference_is_not_silently_fixed_and_second_is_fully_rechecked(self):
        for still_wrong in (False, True):
            with self.subTest(still_wrong=still_wrong), tempfile.TemporaryDirectory() as directory:
                run, env, start, draft = self.prepare(Path(directory), "company")
                original_claim = copy.deepcopy(draft["claims"][0])
                draft["claims"][0]["evidence_refs"] = ["e.unknown"]
                _, repair = self.first(env, start, draft)
                self.assertEqual(repair["allowed_paths"], ["/claims/0"])
                claim = copy.deepcopy(original_claim)
                if still_wrong:
                    claim["evidence_refs"] = ["e.still-unknown"]
                second, _ = self.stop(env, start, {
                    "base_draft_ref": repair["base_draft_ref"],
                    "changes": [{"op": "replace", "path": "/claims/0", "value": claim}],
                })
                self.assertEqual(second["output_capture"]["status"], "FAILED" if still_wrong else "SAVED", second)
                if still_wrong:
                    self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")

    def test_material_document_selection_can_only_be_revised_by_original_author(self):
        for still_wrong in (False, True):
            with self.subTest(still_wrong=still_wrong), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient,
            ):
                run, env, start, draft = self.prepare(Path(directory), "materials")
                original = copy.deepcopy(draft["selections"][0])
                draft["selections"][0]["document_id"] = "nonexistent-document"
                _, repair = self.first(env, start, draft)
                self.assertEqual(repair["allowed_paths"], ["/selections/0"])
                selection = {**original, "document_id": "still-nonexistent"} if still_wrong else original
                second, _ = self.stop(env, start, {
                    "base_draft_ref": repair["base_draft_ref"],
                    "changes": [{"op": "replace", "path": "/selections/0", "value": selection}],
                })
                self.assertEqual(second["output_capture"]["status"], "FAILED" if still_wrong else "SAVED", second)
                if still_wrong:
                    self.assertIn("DOCUMENT_SELECTION_INVALID", second["output_capture"]["failure_code"])
                    self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")

    def test_material_integrity_failure_never_opens_revision(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient,
        ):
            run, env, start, draft = self.prepare(Path(directory), "materials")
            document = next((run / "research/materials").glob("*/document-*.json"))
            document.write_text(document.read_text() + " ")
            record, response = self.stop(env, start, draft)
            self.assertEqual(record["output_capture"]["failure_code"], "RESEARCH_MATERIALS_ARTIFACT_HASH_MISMATCH")
            self.assertEqual(record["output_capture"]["repair_state"], "NOT_ALLOWED")
            self.assertEqual(response, {})
            self.assertNotIn("repair_request", record)

    def test_unparseable_message_cannot_bypass_local_scope_with_whole_new_draft(self):
        for role in ("company", "materials"):
            with self.subTest(role=role), tempfile.TemporaryDirectory() as directory, patch(
                "product.mcp.live.public_research.OpenAlexResearchClient", FakeOpenAlexClient,
            ):
                run, env, start, draft = self.prepare(Path(directory), role)
                first, response = self.stop(env, start, draft, last_assistant_message='{"truncated":')
                self.assertEqual(first["output_capture"]["status"], "FAILED")
                self.assertEqual(first["output_capture"]["repair_state"], "NOT_ALLOWED")
                self.assertEqual(response, {})
                self.assertNotIn("repair_request", first)
                second, _ = self.stop(env, start, draft)
                self.assertEqual(second["output_capture"]["failure_code"], "LOCAL_REVISION_NOT_AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
