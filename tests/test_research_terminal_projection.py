"""真实业务保存、历史收尾与只读展示的状态传播；不模拟正常Hook或模型。"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from product.council.multidimensional_output import (
    project_research_status, render_dimension_report_markdown,
)
from product.runtime import multidimensional_stage as stage
from tests import test_multidimensional_stage as fixtures


class ResearchTerminalProjectionTests(unittest.TestCase):
    def test_not_run_is_not_failed_or_reviewed_or_promoted(self):
        status = project_research_status([])
        self.assertEqual(status["contract_status"], "NOT_RUN")
        self.assertEqual(status["research_review_status"], "NOT_REVIEWED")
        self.assertEqual(status["downstream_status"], "NOT_READY")
        self.assertEqual(status["promotion_status"], "NOT_EVALUATED")
        self.assertEqual(project_research_status([
            {"status": "COMPLETE", "evaluation_status": "PASS"},
        ])["downstream_status"], "STRUCTURALLY_CONSUMABLE")

    def test_legacy_ready_label_cannot_hide_declared_content_failure(self):
        from product.council.multidimensional_research import finalize_research_dimension_report, finalize_holding_research_bundle
        from product.runtime.independent_skeptic_stage import validate_forward_gate, IndependentSkepticStageError
        from tests.test_independent_skeptic_stage import prepare_complete_forward
        with tempfile.TemporaryDirectory() as directory:
            run = prepare_complete_forward(Path(directory))
            bundle_path = run / "research/holding-research-bundle.json"
            bundle = json.loads(bundle_path.read_text())
            ref = next(item for item in bundle["report_refs"] if item["capability"] == "OPTIONS_FLOW")
            path = run / ref["artifact_ref"]
            report = json.loads(path.read_text())
            report["evaluation_status"] = "FAIL"
            report = finalize_research_dimension_report(report)
            path.write_text(json.dumps(report))
            ref["report_hash"] = report["report_hash"]
            bundle["consumability"] = "DOWNSTREAM_READY"
            bundle = finalize_holding_research_bundle(bundle)
            bundle_path.write_text(json.dumps(bundle))
            original = bundle_path.read_bytes()
            proof = stage.check_multidimensional_bundle_consumable(fixtures.ROOT, run, persist=False)
            self.assertEqual(proof["status"], "PASSED")
            self.assertEqual(proof["declared_downstream_status"], "DOWNSTREAM_READY")
            self.assertEqual(proof["downstream_status"], "STRUCTURALLY_CONSUMABLE")
            self.assertTrue(proof["status_projection"]["agent_declared_content_failure"])
            with self.assertRaisesRegex(IndependentSkepticStageError, "COUNTER_FORWARD_DECLARED_CONTENT_FAILURE"):
                validate_forward_gate(fixtures.ROOT, run)
            self.assertEqual(bundle_path.read_bytes(), original)

    def test_author_status_is_projected_identically_from_saved_report_to_browser(self):
        from product.web.read_only import ArtifactCatalog
        from product.web.rendering import _dimension_reports
        helper = fixtures.MultidimensionalStageTests()
        for author_status, evaluation in (("SOURCE_LIMITED", "SOURCE_LIMITED"),
                                          ("INSUFFICIENT_EVIDENCE", "FAIL")):
            with self.subTest(author_status=author_status), tempfile.TemporaryDirectory() as directory:
                run, _ = helper.prepare(Path(directory), count=1)
                index = json.loads((run / "research/dispatch-index.json").read_text())
                task = next(item for item in index["tasks"] if item["capability"] == "OPTIONS_FLOW")
                draft = helper.dimension_draft(task)
                draft.update(status=author_status, evaluation_status=evaluation)
                report, output = helper.save_dimension_fixture(run, task, draft)
                path = Path(output["json"])
                original = path.read_bytes()
                self.assertEqual(json.loads(original), report)
                self.assertFalse((run / "invocation/subagent-events.jsonl").exists())
                status = project_research_status([report])
                self.assertEqual(status["contract_status"], "PASSED")
                self.assertEqual(status["agent_declared_content_failure"], evaluation == "FAIL")
                self.assertEqual(status["source_status"], "SOURCE_LIMITED")
                self.assertEqual(status["research_review_status"], "NOT_REVIEWED")
                self.assertEqual(status["downstream_status"], "STRUCTURALLY_CONSUMABLE")
                catalog = ArtifactCatalog(run_dirs=[run])
                items = catalog.by_kind("dimension_report")
                self.assertEqual(len(items), 1, catalog.issues)
                self.assertEqual(items[0]["status_projection"], status)
                html = _dimension_reports(items)
                self.assertIn(status["research_review_status"], html)
                self.assertIn(status["downstream_status"], html)
                markdown = render_dimension_report_markdown(report, evidence=[])
                self.assertIn("NOT_REVIEWED", markdown)
                self.assertIn(evaluation, markdown)
                self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
