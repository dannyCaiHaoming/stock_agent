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
