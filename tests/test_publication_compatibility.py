"""八维旧发布启动兼容入口必须零副作用拒绝；零模型、零网络。"""
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from product.runtime.nested_codex import launch_nested_codex


class PublicationCompatibilityTests(unittest.TestCase):
    def test_retired_live_and_synthetic_compatibility_cannot_launch_models(self):
        for manifest in ({"source_mode": "live"}, {"compatibility_fixture": True}):
            with self.subTest(manifest=manifest), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "run_manifest.json").write_text(json.dumps({**manifest, "output_dir": str(root), "run_id": "synthetic-retired"}))
                with patch("subprocess.run", side_effect=AssertionError("禁止启动")):
                    with self.assertRaisesRegex(ValueError, 'NATIVE_HOST_EXECUTION_REQUIRED'):
                        launch_nested_codex(Path(__file__).resolve().parents[1], run_dir=root)
                self.assertFalse((root / "invocation").exists())
