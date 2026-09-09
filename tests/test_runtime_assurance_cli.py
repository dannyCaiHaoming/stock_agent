from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.cli import main
from product.runtime.hashing import canonical_hash
from tests.test_replay_capsule import ROOT, complete_run


def invoke(arguments: list[str]) -> tuple[int, dict]:
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = main(arguments)
    lines = [line for line in stdout.getvalue().splitlines() if line.strip()]
    return code, json.loads(lines[-1])


class RuntimeAssuranceCliTests(unittest.TestCase):
    def test_test_evidence_runs_real_subprocess_with_isolated_tmpdir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code, result = invoke([
                "test-evidence", "--repo", str(ROOT),
                "--output-dir", str(root / "test-evidence"),
                "--tmpdir", str(root / "isolated-tmp"),
                "--test-target", "tests.test_runtime_promotion.PromotionEvidenceSmokeTests.test_probe",
            ])
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["tests_run"], 1)
            self.assertEqual(result["environment_errors"], 0)
            self.assertTrue((root / "test-evidence" / "execution-event.json").is_file())

    def test_artifact_replay_and_trace_check_have_machine_readable_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            complete_run(run_dir, "cli-source")
            replay_path = root / "artifact-replay.json"
            code, result = invoke([
                "artifact-replay", "--repo", str(ROOT), "--run-dir", str(run_dir),
                "--output", str(replay_path),
            ])
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "PASSED")
            code, failure = invoke([
                "artifact-replay", "--repo", str(ROOT), "--run-dir", str(run_dir),
                "--output", str(replay_path),
            ])
            self.assertEqual(code, 6)
            self.assertEqual(failure["status"], "FAIL")
            trace_path = root / "trace-integrity.json"
            code, result = invoke([
                "trace-check", "--run-dir", str(run_dir), "--output", str(trace_path),
            ])
            self.assertEqual(code, 0)
            self.assertEqual(result["status"], "PASS")

    def test_failed_regression_verdict_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            index = root / "run-index.json"
            index.write_text("{}\n", encoding="utf-8")
            candidate = json.loads((ROOT / "product" / "version-manifest.json").read_text(encoding="utf-8"))
            code, result = invoke([
                "regression", "--repo", str(ROOT), "--output-dir", str(root / "suite"),
                "--suite-id", "cli-fail", "--candidate-hash", canonical_hash(candidate),
                "--run-index", str(index),
            ])
            self.assertEqual(code, 5)
            self.assertEqual(result["status"], "FAIL")
            report = (root / "suite" / "report.md").read_text(encoding="utf-8")
            self.assertIn(result["reason_codes"][0], report)

    def test_invalid_assurance_input_returns_validation_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variants = root / "variants.json"
            variants.write_text(json.dumps({"score": 1}), encoding="utf-8")
            code, result = invoke([
                "ablation", "--repo", str(ROOT), "--output-dir", str(root / "out"),
                "--ablation-id", "invalid", "--variants", str(variants),
            ])
            self.assertEqual(code, 6)
            self.assertEqual(result["command"], "ablation")
            self.assertTrue(result["reason_code"])


if __name__ == "__main__":
    unittest.main()
