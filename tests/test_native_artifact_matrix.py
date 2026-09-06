from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from product.runtime.artifact_matrix import ArtifactMatrixError, validate_artifact_matrix
from product.runtime.run_package import finalize_cio, prepare_cio, prepare_run
from tests.test_native_run_package import FIXTURES, ROOT, cio_output, specialist_outputs, write_json


class NativeArtifactMatrixTests(unittest.TestCase):
    def test_published_chain_and_pre_agent_no_trade_have_valid_matrices(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            chain = root / "chain"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=chain,
                run_id="matrix-chain",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(chain)
            prepare_cio(ROOT, run_dir=chain, model="gpt-5.6-terra")
            write_json(chain / "cio" / "runtime_cio.json", cio_output(chain))
            finalize_cio(ROOT, run_dir=chain)
            self.assertEqual(
                validate_artifact_matrix(chain, require_eval=False)["status"], "PASSED"
            )

            safe = root / "safe"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "future-or-stale.json",
                run_dir=safe,
                run_id="matrix-safe",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
            )
            self.assertEqual(
                validate_artifact_matrix(safe, require_eval=False)["status"], "PASSED"
            )

    def test_missing_required_chain_artifact_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "chain"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="matrix-missing",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
            finalize_cio(ROOT, run_dir=run_dir)
            (run_dir / "agents" / "runtime_skeptic.json").unlink()
            with self.assertRaisesRegex(ArtifactMatrixError, "ARTIFACT_MATRIX_FAILED"):
                validate_artifact_matrix(run_dir, require_eval=False)


if __name__ == "__main__":
    unittest.main()
