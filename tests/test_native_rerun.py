from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.native_rerun import NativeRerunError, prepare_native_rerun
from product.runtime.run_package import prepare_run
from tests.test_native_run_package import FIXTURES, ROOT


class NativeRerunTests(unittest.TestCase):
    def test_new_run_id_preserves_fixture_model_and_version_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            rerun = root / "rerun"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=source,
                run_id="source-run",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
            )
            result = prepare_native_rerun(
                ROOT,
                source_run_dir=source,
                new_run_dir=rerun,
                new_run_id="rerun-001",
            )
            self.assertEqual(result["next_state"], "DISPATCH_REQUIRED")
            manifest = json.loads(
                (rerun / "native-rerun-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["source_run_id"], "source-run")
            self.assertEqual(manifest["new_run_id"], "rerun-001")
            self.assertFalse(manifest["llm_output_equality_required"])
            self.assertTrue(manifest["contract_and_semantic_eval_required"])

    def test_resource_drift_blocks_rerun_before_new_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=source,
                run_id="source-run",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
            )
            manifest_path = source / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["discovery"]["discovery_hash"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            new_dir = root / "blocked"
            with self.assertRaisesRegex(NativeRerunError, "VERSION_DRIFT"):
                prepare_native_rerun(
                    ROOT,
                    source_run_dir=source,
                    new_run_dir=new_dir,
                    new_run_id="rerun-blocked",
                )
            self.assertFalse(new_dir.exists())


if __name__ == "__main__":
    unittest.main()
