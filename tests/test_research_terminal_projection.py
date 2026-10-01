"""真实本地 Hook/收尾器的失败传播；只替换外部进程，不调用模型。"""
from __future__ import annotations

import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from product.council.multidimensional_output import (
    project_research_status, render_dimension_report_markdown,
)
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime import multidimensional_stage as stage
from tests import test_multidimensional_stage as fixtures


class ResearchTerminalProjectionTests(unittest.TestCase):
    def test_exit_zero_with_six_saved_one_failed_one_unstarted_is_not_stage_pass(self):
        self._assert_partial_terminal(interrupted=False)

    def test_user_interrupt_preserves_six_saved_one_failed_one_dependency_blocked(self):
        self._assert_partial_terminal(interrupted=True)

    def _assert_partial_terminal(self, *, interrupted):
        helper = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = helper.prepare(Path(directory), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())

            def fake_process(command, *, input, cwd, env, **kwargs):
                for number, task in enumerate(index["tasks"]):
                    dispatch = helper.dispatch_payload(task, parent="projection-parent")
                    dispatch["tool_use_id"] = f"projection-dispatch-{number}"
                    dispatched, _ = handle_hook_event(dispatch, environ=env)
                    if task["capability"] == "RESEARCH_REPORT":
                        self.assertEqual(dispatched["decision"], "DENY_DISPATCH_CONTRACT")
                        continue
                    self.assertEqual(dispatched["decision"], "ALLOW", dispatched)
                    child = f"projection-child-{number}"
                    started, _ = handle_hook_event(helper.start_payload(task, parent="projection-parent", child=child), environ=env)
                    self.assertEqual(started["context_binding"]["status"], "DELIVERED", started)
                    draft = helper.dimension_draft(task, include_impact=task["capability"] != "FUNDAMENTAL_EVENT")
                    payload = helper.stop_payload(task, draft, parent="projection-parent", child=child)
                    stopped, _ = handle_hook_event(payload, environ=env)
                    if task["capability"] == "FUNDAMENTAL_EVENT":
                        self.assertEqual(stopped["hook_event_name"], "SubagentStopBlocked", stopped)
                        stopped, _ = handle_hook_event(payload, environ=env)
                        self.assertEqual(stopped["output_capture"]["repair_state"], "EXHAUSTED", stopped)
                    else:
                        self.assertEqual(stopped["output_capture"]["status"], "SAVED", stopped)
                if interrupted:
                    raise KeyboardInterrupt
                (Path(env["TMPDIR"]) / "final-message.json").write_text(json.dumps({
                    "stage": "MULTI_DIMENSIONAL_HOLDING_RESEARCH", "run_id": index["run_id"],
                    "dispatched": len(index["tasks"]), "completed": len(index["tasks"]),
                }))
                return subprocess.CompletedProcess(command, 0, "", "")

            with patch.object(stage.subprocess, "run", side_effect=fake_process) as process:
                from product.runtime.cli import main
                output = io.StringIO()
                with redirect_stdout(output):
                    code = main(["launch-multidimensional-research", "--repo", str(fixtures.ROOT),
                                 "--run-dir", str(run)])
                result = json.loads(output.getvalue())
            self.assertEqual(process.call_count, 1)
            self.assertEqual(result["status"], "USER_INTERRUPTED" if interrupted else "FAILED", result)
            self.assertEqual(code, 130 if interrupted else 7)
            saved_process = json.loads((run / "invocation/process-result.json").read_text())
            self.assertEqual(saved_process["process_exit_code"], None if interrupted else 0)
            self.assertEqual(saved_process["stage_status"], result["status"])
            self.assertEqual(saved_process["failure_code"],
                             "MULTIDIMENSIONAL_USER_INTERRUPTED" if interrupted else "MULTIDIMENSIONAL_TASK_VALIDATION_FAILED")
            self.assertEqual(saved_process["interrupted"], interrupted)
            self.assertEqual(saved_process["captured_process_output_complete"], not interrupted)
            self.assertEqual(saved_process["saved_task_count"], 6)
            statuses = [item["status"] for item in saved_process["task_outcomes"]]
            self.assertEqual(statuses.count("FAILED"), 1)
            self.assertEqual(statuses.count("DEPENDENCY_BLOCKED"), 1)
            self.assertTrue((run / "research/holding-research-bundle.json").is_file())
            bundle = json.loads((run / "research/holding-research-bundle.json").read_text())
            self.assertEqual(bundle["consumability"], "STRUCTURALLY_CONSUMABLE")
            self.assertEqual(result["research_review_status"], "NOT_REVIEWED")
            self.assertEqual(result["promotion_status"], "NOT_EVALUATED")
            self.assertEqual(result["status_projection"]["process_status"],
                             "USER_INTERRUPTED" if interrupted else "EXITED")
            self.assertEqual(saved_process["status_projection"], result["status_projection"])
            proof = stage.check_multidimensional_bundle_consumable(fixtures.ROOT, run, persist=False)
            self.assertEqual(proof["status_projection"]["contract_status"], "FAILED")
            self.assertEqual(proof["downstream_status"], "STRUCTURALLY_CONSUMABLE")
            self.assertEqual(proof["status_projection"], result["status_projection"])
            from product.web.read_only import ArtifactCatalog
            catalog = ArtifactCatalog(run_dirs=[run])
            for item in catalog.by_kind("dimension_report"):
                self.assertEqual(item["status_projection"]["process_status"],
                                 result["status_projection"]["process_status"])
            markdown = (run / "research/holding-research-bundle.md").read_text()
            self.assertIn(result["status_projection"]["process_status"], markdown)

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

    def test_interrupt_after_start_does_not_invent_failed_stop(self):
        helper = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = helper.prepare(Path(directory), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = index["tasks"][0]

            def interrupted_process(command, *, env, **kwargs):
                handle_hook_event(helper.dispatch_payload(task, parent="interrupt-parent"), environ=env)
                handle_hook_event(helper.start_payload(task, parent="interrupt-parent", child="interrupt-child"), environ=env)
                raise KeyboardInterrupt

            with patch.object(stage.subprocess, "run", side_effect=interrupted_process):
                result, code = stage.launch_multidimensional_stage(fixtures.ROOT, run_dir=run)
            self.assertEqual((result["status"], code), ("USER_INTERRUPTED", 130))
            process = json.loads((run / "invocation/process-result.json").read_text())
            self.assertEqual(process["failed_task_count"], 0)
            self.assertEqual(process["task_outcomes"][0]["status"], "STARTED_NO_TERMINAL")
            self.assertTrue(all(item["status"] == "NOT_DISPATCHED" for item in process["task_outcomes"][1:]))
            self.assertEqual(result["status_projection"]["contract_status"], "INCOMPLETE")
            if (run / "research/holding-research-bundle.json").is_file():
                bundle = json.loads((run / "research/holding-research-bundle.json").read_text())
                self.assertTrue(all(item["status"] == "NOT_RESEARCHED" for item in bundle["coverage"]))

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
                env = helper.targeted_environment(run, task)
                dispatched, _ = handle_hook_event(helper.dispatch_payload(task, parent="status-parent"), environ=env)
                self.assertEqual(dispatched["decision"], "ALLOW", dispatched)
                handle_hook_event(helper.start_payload(task, parent="status-parent", child="status-child"), environ=env)
                draft = helper.dimension_draft(task)
                draft.update(status=author_status, evaluation_status=evaluation)
                stopped, _ = handle_hook_event(helper.stop_payload(task, draft, parent="status-parent", child="status-child"), environ=env)
                self.assertEqual(stopped["output_capture"]["status"], "SAVED", stopped)
                path = run / stopped["output_capture"]["path"]
                original = path.read_bytes()
                report = json.loads(original)
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
