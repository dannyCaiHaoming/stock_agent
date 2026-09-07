from __future__ import annotations

import copy
import contextlib
import ast
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.artifact_matrix import ArtifactMatrixError, validate_artifact_matrix
from product.runtime.cli import main as runtime_cli_main
from product.runtime.native_eval import evaluate_run, persist_eval_result
from product.runtime.release_gate import check_run
from product.runtime.replay import replay_run
from product.runtime.hashing import file_hash
from product.runtime.run_package import (
    RunPackageError,
    finalize_cio,
    prepare_cio,
    prepare_run,
)
from product.runtime.terminal_contract import (
    FailureStage,
    failure_stage_required_files,
)
from product.runtime.trace_validation import TraceValidationError, validate_decision_trace
from tests.test_native_run_package import (
    FIXTURES,
    ROOT,
    cio_output,
    read_json,
    specialist_outputs,
    write_json,
)


def _prepare_chain(run_dir: Path, run_id: str) -> None:
    prepare_run(
        ROOT,
        fixture_path=FIXTURES / "normal-research.json",
        run_dir=run_dir,
        run_id=run_id,
        model="gpt-5.6-terra",
        research_question="研究 fixture。",
        authenticity_required=False,
    )
    specialist_outputs(run_dir)
    prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")


def _no_trade_draft(run_dir: Path, *, maximum_notional=None, target=None):
    draft = cio_output(run_dir)
    draft.update(
        {
            "status": "LOW_CONFIDENCE",
            "action": "NO_TRADE",
            "target_weight_range": target,
            "maximum_notional": maximum_notional,
            "no_trade_reason": "EVIDENCE_CONFLICT",
            "no_trade_explanation": "关键证据冲突尚未解决。",
            "reevaluation_conditions": ["获得可核验的新证据。"],
        }
    )
    return draft


class FailureStageTraceTests(unittest.TestCase):
    def test_every_fail_run_call_declares_a_failure_stage(self):
        call_count = 0
        for relative in ("product/runtime/run_package.py", "product/runtime/cli.py"):
            tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "fail_run":
                    call_count += 1
                    self.assertIn("failed_stage", {item.arg for item in node.keywords})
        self.assertGreater(call_count, 0)

    def test_all_nine_failure_stages_have_monotonic_artifact_contracts(self):
        previous: set[str] = set()
        self.assertEqual(len(FailureStage), 9)
        for stage in FailureStage:
            required = failure_stage_required_files(stage)
            self.assertTrue(previous <= required, stage)
            previous = required
        self.assertNotIn(
            "risk/check-1.json",
            failure_stage_required_files(FailureStage.RISK_ENGINE),
        )
        self.assertIn(
            "risk/check-1.json",
            failure_stage_required_files(FailureStage.PUBLICATION_VALIDATION),
        )

    def test_artifact_matrix_accepts_each_declared_failure_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for stage in FailureStage:
                run_dir = root / stage.value.casefold()
                run_dir.mkdir()
                run_id = f"stage-{stage.value.casefold()}"
                error = {
                    "schema_version": "run-error/2.1.0",
                    "run_id": run_id,
                    "terminal_state": "FAILED_VALIDATION",
                    "failed_stage": stage.value,
                    "code": "TEST_FAILURE",
                    "message": "确定性阶段矩阵测试。",
                }
                write_json(run_dir / "run_error.json", error)
                required = failure_stage_required_files(stage)
                for relative in required:
                    path = run_dir / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if relative == "run_manifest.json":
                        write_json(
                            path,
                            {
                                "run_id": run_id,
                                "authenticity_required": False,
                            },
                        )
                    elif path.suffix == ".json":
                        write_json(path, {})
                    else:
                        path.write_text("stage artifact\n", encoding="utf-8")
                traced_files = {"run_error.json", *required}
                trace = {
                    "schema_version": "decision-trace/2.1.0",
                    "run_id": run_id,
                    "terminal_state": "FAILED_VALIDATION",
                    "failed_stage": stage.value,
                    "runtime": {},
                    "agents": [],
                    "events": [
                        {
                            "stage": "VALIDATION_FAILED",
                            "failed_stage": stage.value,
                            "code": "TEST_FAILURE",
                        }
                    ],
                    "risk_lineage": [],
                    "artifacts": {
                        relative: file_hash(run_dir / relative)
                        for relative in traced_files
                    },
                    "codex_execution": None,
                    "mcp_events": [],
                    "evidence_lineage": None,
                }
                write_json(run_dir / "decision_trace.json", trace)
                self.assertEqual(
                    validate_artifact_matrix(run_dir, require_eval=False)["status"],
                    "PASSED",
                    stage,
                )

    def test_pre_risk_invalid_no_trade_is_trace_valid_and_diagnosable(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "invalid-no-trade"
            _prepare_chain(run_dir, "invalid-no-trade")
            write_json(
                run_dir / "cio" / "runtime_cio.json",
                _no_trade_draft(run_dir, maximum_notional=0),
            )
            result = finalize_cio(ROOT, run_dir=run_dir)
            self.assertEqual(result["terminal_state"], "FAILED_VALIDATION")
            error = read_json(run_dir / "run_error.json")
            trace = read_json(run_dir / "decision_trace.json")
            self.assertEqual(error["failed_stage"], "CIO_VALIDATION")
            self.assertEqual(trace["failed_stage"], "CIO_VALIDATION")
            self.assertEqual(trace["risk_lineage"], [])
            self.assertIn("NO_TRADE_EXECUTION_FIELDS_FORBIDDEN", error["message"])
            validate_decision_trace(trace, run_dir=run_dir)
            validate_artifact_matrix(run_dir, require_eval=False)
            before_replay = {
                str(path.relative_to(run_dir)): path.read_bytes()
                for path in run_dir.rglob("*")
                if path.is_file()
            }
            replay = replay_run(ROOT, run_dir=run_dir)
            after_replay = {
                str(path.relative_to(run_dir)): path.read_bytes()
                for path in run_dir.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before_replay, after_replay)
            self.assertEqual(replay["status"], "PASSED")
            self.assertEqual(replay["failed_stage"], "CIO_VALIDATION")
            gate, exit_code = check_run(ROOT, run_dir=run_dir)
            self.assertEqual(exit_code, 2)
            self.assertEqual(gate["category"], "FAILED_VALIDATION")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cli_exit = runtime_cli_main(
                    ["check-run", "--repo", str(ROOT), "--run-dir", str(run_dir)]
                )
            self.assertEqual(cli_exit, 2)
            self.assertEqual(json.loads(stdout.getvalue())["failed_stage"], "CIO_VALIDATION")
            self.assertFalse((run_dir / "decision.json").exists())
            self.assertFalse((run_dir / "report.md").exists())

    def test_legal_no_trade_reaches_risk_and_publishes(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "legal-no-trade"
            _prepare_chain(run_dir, "legal-no-trade")
            write_json(
                run_dir / "cio" / "runtime_cio.json", _no_trade_draft(run_dir)
            )
            result = finalize_cio(ROOT, run_dir=run_dir)
            self.assertEqual(result["next_state"], "SAFE_NO_TRADE")
            trace = read_json(run_dir / "decision_trace.json")
            self.assertIsNone(trace["failed_stage"])
            self.assertEqual(trace["risk_lineage"][-1]["status"], "COMPLETED")
            self.assertIsNone(
                read_json(run_dir / "decision.json")["decisions"][0][
                    "maximum_notional"
                ]
            )

    def test_risk_failure_requires_failed_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "risk-failure"
            _prepare_chain(run_dir, "risk-failure")
            write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
            with patch(
                "product.runtime.run_package.check_cio_draft",
                side_effect=ValueError("deterministic risk failure"),
            ):
                result = finalize_cio(ROOT, run_dir=run_dir)
            self.assertEqual(result["failed_stage"], "RISK_ENGINE")
            trace = read_json(run_dir / "decision_trace.json")
            self.assertEqual(trace["risk_lineage"][-1]["status"], "FAILED")
            validate_decision_trace(trace, run_dir=run_dir)
            replay_run(ROOT, run_dir=run_dir)

            trace["risk_lineage"] = []
            (run_dir / "decision_trace.json").write_text(
                json.dumps(trace), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                TraceValidationError, "TRACE_RISK_LINEAGE_MISSING"
            ):
                validate_decision_trace(trace, run_dir=run_dir)

    def test_publication_failure_keeps_completed_risk_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "publication-failure"
            _prepare_chain(run_dir, "publication-failure")
            write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
            with patch(
                "product.runtime.run_package.verify_integrity",
                side_effect=RunPackageError("integrity failure"),
            ):
                result = finalize_cio(ROOT, run_dir=run_dir)
            self.assertEqual(result["failed_stage"], "PUBLICATION_VALIDATION")
            trace = read_json(run_dir / "decision_trace.json")
            self.assertEqual(trace["risk_lineage"][-1]["status"], "COMPLETED")
            validate_decision_trace(trace, run_dir=run_dir)
            validate_artifact_matrix(run_dir, require_eval=False)

    def test_trace_run_error_mismatch_and_legacy_version_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "mismatch"
            _prepare_chain(run_dir, "mismatch")
            write_json(
                run_dir / "cio" / "runtime_cio.json",
                _no_trade_draft(run_dir, target=[0, 0]),
            )
            finalize_cio(ROOT, run_dir=run_dir)
            trace = read_json(run_dir / "decision_trace.json")
            old = copy.deepcopy(trace)
            old["schema_version"] = "decision-trace/2.0.0"
            with self.assertRaisesRegex(TraceValidationError, "SCHEMA_VERSION"):
                validate_decision_trace(old, run_dir=run_dir)
            self.assertEqual(old["schema_version"], "decision-trace/2.0.0")

            error = read_json(run_dir / "run_error.json")
            error["failed_stage"] = "RISK_ENGINE"
            (run_dir / "run_error.json").write_text(json.dumps(error), encoding="utf-8")
            with self.assertRaisesRegex(
                (TraceValidationError, ArtifactMatrixError), "MISMATCH|UNRESOLVED"
            ):
                validate_decision_trace(trace, run_dir=run_dir)

    def test_failed_replay_rejects_missing_required_and_forbidden_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "missing"
            _prepare_chain(missing, "missing")
            write_json(
                missing / "cio" / "runtime_cio.json",
                _no_trade_draft(missing, maximum_notional=0),
            )
            finalize_cio(ROOT, run_dir=missing)
            (missing / "prompts" / "runtime_cio.txt").unlink()
            with self.assertRaisesRegex(ValueError, "ARTIFACT|UNRESOLVED"):
                replay_run(ROOT, run_dir=missing)

            forbidden = root / "forbidden"
            _prepare_chain(forbidden, "forbidden")
            write_json(
                forbidden / "cio" / "runtime_cio.json",
                _no_trade_draft(forbidden, maximum_notional=0),
            )
            finalize_cio(ROOT, run_dir=forbidden)
            write_json(forbidden / "decision.json", {"not": "allowed"})
            with self.assertRaisesRegex(ValueError, "ARTIFACT_MATRIX_FAILED"):
                replay_run(ROOT, run_dir=forbidden)


class ReleaseGateTests(unittest.TestCase):
    def test_completed_safe_no_trade_requires_actual_eval(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "stale"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "future-or-stale.json",
                run_dir=run_dir,
                run_id="gate-stale",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
            )
            missing, exit_code = check_run(ROOT, run_dir=run_dir)
            self.assertEqual(exit_code, 4)
            self.assertEqual(missing["category"], "EVAL_MISSING_OR_FAILED")

            evaluated = evaluate_run(ROOT, run_dir=run_dir)
            persist_eval_result(evaluated, run_dir=run_dir)
            passed, exit_code = check_run(ROOT, run_dir=run_dir)
            self.assertEqual(exit_code, 0)
            self.assertEqual(passed["status"], "PASSED")
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                cli_exit = runtime_cli_main(
                    ["check-run", "--repo", str(ROOT), "--run-dir", str(run_dir)]
                )
            self.assertEqual(cli_exit, 0)
            self.assertEqual(json.loads(stdout.getvalue())["status"], "PASSED")

    def test_nonterminal_or_malformed_run_returns_three(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "empty"
            run_dir.mkdir()
            result, exit_code = check_run(ROOT, run_dir=run_dir)
            self.assertEqual(exit_code, 3)
            self.assertEqual(result["category"], "INVALID_OR_INCOMPLETE_RUN")


if __name__ == "__main__":
    unittest.main()
