from __future__ import annotations

import json
from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from product.runtime.hashing import canonical_hash
from product.runtime.run_package import prepare_cio, prepare_run
from product.runtime.runtime_eval import (
    SEMANTIC_DIMENSIONS,
    RuntimeEvalError,
    finalize_eval_job,
    prepare_eval_job,
    render_eval_report,
    validate_not_applicable_semantic_result,
    validate_semantic_result,
    verify_runtime_eval_job,
)
from tests.test_native_run_package import FIXTURES, ROOT, read_json, specialist_outputs
from tests.test_replay_capsule import complete_run


def semantic_result(eval_dir: Path, *, status: str = "PASS", grade: int = 2) -> dict:
    manifest = read_json(eval_dir / "input-manifest.json")
    value = {
        "schema_version": "semantic-rubric-result/1.0.0",
        "eval_id": manifest["eval_id"],
        "grader": {
            "agent": "dev_eval",
            "model": manifest.get("grader_model", "gpt-5.6-sol"),
            "prompt_hash": manifest["source_hashes"]["grader_prompt"],
            "rubric_hash": manifest["source_hashes"]["rubric"],
            "input_hash": manifest["source_hashes"]["semantic_input"],
        },
        "dimensions": {
            name: {
                "status": status,
                "grade": grade,
                "evidence_refs": [],
                "rationale": "人工校准用结构化评分。",
            }
            for name in SEMANTIC_DIMENSIONS
        },
    }
    value["output_hash"] = canonical_hash(value)
    return value


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


class RuntimeEvalJobTests(unittest.TestCase):
    def test_external_eval_reads_real_run_without_mutating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            eval_dir = root / "eval-job"
            complete_run(run_dir, "eval-source")
            before = {str(path.relative_to(run_dir)): path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
            prepared = prepare_eval_job(ROOT, run_dir=run_dir, eval_dir=eval_dir, eval_id="eval-1")
            self.assertEqual(prepared["next_state"], "SEMANTIC_GRADING_REQUIRED")
            grader = root / "grader.json"
            write_json(grader, semantic_result(eval_dir))
            result = finalize_eval_job(ROOT, eval_dir=eval_dir, semantic_result_path=grader)
            self.assertEqual(result["status"], "PASS")
            self.assertTrue((eval_dir / "eval" / "result.json").is_file())
            self.assertEqual((eval_dir / "eval" / "report.md").read_text(), render_eval_report(result))
            report = (eval_dir / "eval" / "report.md").read_text(encoding="utf-8")
            self.assertIn(result["grader"]["prompt_hash"], report)
            self.assertIn(result["grader"]["rubric_hash"], report)
            after = {str(path.relative_to(run_dir)): path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_semantic_grader_lineage_is_required_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            eval_dir = root / "eval-job"
            complete_run(run_dir, "eval-lineage")
            prepare_eval_job(ROOT, run_dir=run_dir, eval_dir=eval_dir, eval_id="eval-lineage")
            with self.assertRaisesRegex(RuntimeEvalError, "SEMANTIC_RESULT_REQUIRED"):
                finalize_eval_job(ROOT, eval_dir=eval_dir)
            bad = semantic_result(eval_dir)
            bad["grader"]["prompt_hash"] = "0" * 64
            body = dict(bad)
            body.pop("output_hash")
            bad["output_hash"] = canonical_hash(body)
            grader = root / "bad-grader.json"
            write_json(grader, bad)
            with self.assertRaisesRegex(RuntimeEvalError, "GRADER_LINEAGE"):
                finalize_eval_job(ROOT, eval_dir=eval_dir, semantic_result_path=grader)

    def test_expected_failed_validation_is_diagnosable_without_risk_lineage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "failed"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="eval-failed",
                model="gpt-6-luna",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            report = read_json(run_dir / "agents" / "runtime_company_analyst.json")
            report["claims"][0]["evidence_refs"] = ["dangling"]
            write_json(run_dir / "agents" / "runtime_company_analyst.json", report)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-6-luna")
            error = read_json(run_dir / "run_error.json")
            self.assertEqual("SPECIALIST_REPORT_VALIDATION_FAILED", error["code"])
            self.assertEqual("EVIDENCE_CLOSURE_FAILED:dangling", error["message"])
            self.assertFalse((run_dir / "decision.json").exists())
            eval_dir = root / "failed-eval"
            prepared = prepare_eval_job(
                ROOT,
                run_dir=run_dir,
                eval_dir=eval_dir,
                eval_id="eval-failed",
                expected_terminal_states=("FAILED_VALIDATION",),
            )
            self.assertEqual(prepared["next_state"], "READY_TO_FINALIZE")
            result = finalize_eval_job(ROOT, eval_dir=eval_dir)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["hard_gates"]["risk_bypass"]["risk_attempts"], 0)
            verified = verify_runtime_eval_job(ROOT, eval_result_path=eval_dir / "eval/result.json")
            self.assertEqual(verified["status"], "PASS")
            manifest = read_json(eval_dir / "input-manifest.json")
            semantic = read_json(eval_dir / "semantic-rubric.json")
            validate_not_applicable_semantic_result(semantic, repository_root=ROOT, input_manifest=manifest)
            # Deterministic not-applicable is never accepted as model grading.
            with self.assertRaisesRegex(RuntimeEvalError, "SEMANTIC_GRADER_LINEAGE_INVALID"):
                validate_semantic_result(semantic, eval_id=manifest["eval_id"], input_manifest=manifest)
            for field, value in (("model", "gpt-6-luna"), ("prompt_hash", "0" * 64)):
                bad = deepcopy(semantic)
                bad["grader"][field] = value
                bad["output_hash"] = canonical_hash({k: v for k, v in bad.items() if k != "output_hash"})
                with self.subTest(field=field), self.assertRaisesRegex(RuntimeEvalError, "EVAL_NOT_APPLICABLE_RESULT_INVALID"):
                    validate_not_applicable_semantic_result(bad, repository_root=ROOT, input_manifest=manifest)
            for field, value in (("status", "PASS"), ("grade", 0), ("evidence_refs", ["invented"])):
                bad = deepcopy(semantic)
                bad["dimensions"][SEMANTIC_DIMENSIONS[0]][field] = value
                bad["output_hash"] = canonical_hash({k: v for k, v in bad.items() if k != "output_hash"})
                with self.subTest(field=field), self.assertRaisesRegex(RuntimeEvalError, "EVAL_NOT_APPLICABLE_RESULT_INVALID"):
                    validate_not_applicable_semantic_result(bad, repository_root=ROOT, input_manifest=manifest)

    def test_hard_gate_failure_cannot_be_averaged_away(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            eval_dir = root / "eval-job"
            complete_run(run_dir, "eval-hard-gate")
            prepare_eval_job(ROOT, run_dir=run_dir, eval_dir=eval_dir, eval_id="eval-hard-gate")
            deterministic_path = eval_dir / "deterministic.json"
            deterministic = read_json(deterministic_path)
            deterministic["hard_gates"]["pit_leakage"] = {"status": "FAIL", "leak_count": 1}
            deterministic_path.write_text(json.dumps(deterministic), encoding="utf-8")
            grader = root / "grader.json"
            write_json(grader, semantic_result(eval_dir, grade=3))
            result = finalize_eval_job(ROOT, eval_dir=eval_dir, semantic_result_path=grader)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("HARD_GATE_FAILED:pit_leakage", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
