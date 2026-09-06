from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from product.runtime.replay import ReplayError, replay_run, write_replay_result
from product.runtime.run_package import finalize_cio, prepare_cio, prepare_run
from tests.test_native_run_package import FIXTURES, ROOT, cio_output, specialist_outputs, write_json


class NativeReplayTests(unittest.TestCase):
    def test_artifact_replay_is_repeatable_without_an_llm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "run"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="replay-source",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
            finalize_cio(ROOT, run_dir=run_dir)
            first = replay_run(ROOT, run_dir=run_dir)
            second = replay_run(ROOT, run_dir=run_dir)
            self.assertEqual(first, second)
            self.assertEqual(first["status"], "PASSED")
            output = root / "replay" / "result.json"
            write_replay_result(first, output_path=output)
            with self.assertRaisesRegex(ReplayError, "ALREADY_EXISTS"):
                write_replay_result(first, output_path=output)

    def test_replay_detects_tampered_report(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "safe"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "future-or-stale.json",
                run_dir=run_dir,
                run_id="replay-tamper",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
            )
            (run_dir / "report.md").write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                replay_run(ROOT, run_dir=run_dir)


if __name__ == "__main__":
    unittest.main()
