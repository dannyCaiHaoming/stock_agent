"""八维发布拆分的旧 Skeptic 格式修复接缝；零模型、零网络。"""
import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from product.runtime.codex_hook_recorder import _skeptic_repair_packet
from product.runtime.nested_codex import launch_nested_codex


class PublicationCompatibilityTests(unittest.TestCase):
    def test_retired_live_and_synthetic_compatibility_cannot_launch_models(self):
        for manifest in ({"source_mode": "live"}, {"compatibility_fixture": True}):
            with self.subTest(manifest=manifest), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "run_manifest.json").write_text(json.dumps({**manifest, "output_dir": str(root), "run_id": "synthetic-retired"}))
                with patch("product.runtime.nested_codex.subprocess.run", side_effect=AssertionError("禁止启动")):
                    with self.assertRaisesRegex(ValueError, "LIVE_COUNCIL_ENTRY_RETIRED"):
                        launch_nested_codex(Path(__file__).resolve().parents[1], run_dir=root)
                self.assertFalse((root / "invocation").exists())

    def call(self, *, attempt=1, failure="SCHEMA_TYPE_INVALID", message=None):
        task = {"task_id": "skeptic:synthetic", "task_name": "skeptic_1", "invocation_id": "inv-1"}
        module = SimpleNamespace(build_skeptic_dispatch_packet=lambda *a, **k: {"output_schema": {"type": "object"}})
        with patch("product.runtime.codex_hook_recorder._research_index", return_value={"tasks": [task]}), patch(
            "product.runtime.codex_hook_recorder._independent_skeptic_module", return_value=module,
        ):
            return _skeptic_repair_packet(
                {"last_assistant_message": message if message is not None else json.dumps({"invocation_id": "inv-1", "summary": "研究原文"})},
                {"STOCK_AGENT_RUN_DIR": "/private/tmp/synthetic-unwritten-run"},
                attempt=attempt, failure_code=failure,
            )

    def test_first_legacy_format_error_keeps_original_draft(self):
        result = self.call()
        self.assertEqual(result["repair_contract"], "independent-skeptic-format-repair/1.0.0")
        self.assertEqual(result["original_draft"]["summary"], "研究原文")
        self.assertEqual(result["maximum_submissions"], 2)

    def test_second_attempt_and_semantic_error_never_get_format_repair(self):
        self.assertIsNone(self.call(attempt=2))
        self.assertIsNone(self.call(failure="COUNTER_REPORT_EVIDENCE_DANGLING"))

    def test_missing_wrong_identity_or_non_json_never_get_repair(self):
        for message in ("", "not-json", "[]", json.dumps({"invocation_id": "other"})):
            with self.subTest(message=message):
                self.assertIsNone(self.call(message=message))
