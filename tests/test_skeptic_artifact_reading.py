"""反证冻结任务的只读绑定：真实准备/Hook 接缝，零模型。"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime import independent_skeptic_stage as stage
from product.runtime.hashing import file_hash, canonical_hash
from tests import test_skeptic_semantic_handoff as semantic


def snapshot(root):
    return {str(path.relative_to(root)): file_hash(path)
            for path in root.rglob("*") if path.is_file()}


class SkepticArtifactReadingTests(unittest.TestCase):
    def prepare(self, directory):
        run, task, _, _, _ = semantic.SkepticSemanticHandoffTests().prepare(directory)
        gate = json.loads((run / "evidence/gate.json").read_text())
        return run, task, gate

    def read(self, run, task, gate, **kwargs):
        return stage.resolve_skeptic_tool_scope(
            run, run_id=gate["run_id"], invocation_id=task["invocation_id"], gate=gate, **kwargs)

    def test_moved_task_uses_frozen_relative_schema_not_current_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, gate = self.prepare(directory)
            before = snapshot(run)
            moved = Path(directory) / "copied-history"
            shutil.copytree(run, moved)
            shutil.rmtree(run)
            with patch("product.runtime.invocation.verify_invocation_manifest", side_effect=AssertionError("不能授权当前执行")) as verify:
                path, allowed = self.read(moved, task, gate, for_execution=False)
                verify.assert_not_called()
            self.assertEqual(path, moved / task["invocation_ref"])
            self.assertEqual(allowed, task["allowed_evidence_ids"])
            self.assertEqual(snapshot(moved), before)
            with self.assertRaises((ValueError, OSError)):
                self.read(moved, task, gate)  # MCP 默认仍是当前执行准入。

    def test_missing_or_tampered_dependencies_are_not_recovered(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, gate = self.prepare(directory)
            original = snapshot(run)
            for defect, field in (("missing", "schema_ref"), ("tamper", "schema_ref"),
                                  ("tamper", "prompt_ref"), ("tamper", "input_ref"),
                                  ("symlink", "schema_ref")):
                with self.subTest(defect=defect, field=field), tempfile.TemporaryDirectory() as copied:
                    target = Path(copied) / "history"
                    shutil.copytree(run, target)
                    dependency = target / task[field]
                    if defect == "missing":
                        dependency.unlink()
                    elif defect == "symlink":
                        outside = Path(copied) / "outside.json"
                        shutil.copyfile(dependency, outside)
                        dependency.unlink()
                        dependency.symlink_to(outside)
                    else:
                        dependency.write_text("{}")
                    before = snapshot(target)
                    with self.assertRaises(stage.IndependentSkepticStageError):
                        self.read(target, task, gate, for_execution=False)
                    self.assertEqual(snapshot(target), before)
            self.assertEqual(snapshot(run), original)

    def test_unknown_frozen_schema_version_is_not_treated_as_current(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, gate = self.prepare(directory)
            schema_path = run / task["schema_ref"]
            schema = json.loads(schema_path.read_text())
            schema["$id"] = "portfolio-council/counter-thesis-report/99.0.0"
            schema_path.write_text(json.dumps(schema))
            path = run / task["invocation_ref"]
            invocation = json.loads(path.read_text())
            invocation["output_schema_hash"] = file_hash(schema_path)
            invocation["manifest_hash"] = canonical_hash({key: value for key, value in invocation.items() if key != "manifest_hash"})
            path.write_text(json.dumps(invocation))
            before = snapshot(run)
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "UNSUPPORTED_VERSION"):
                self.read(run, task, gate, for_execution=False)
            self.assertEqual(snapshot(run), before)

    def test_actual_formal_package_is_readable_after_source_directory_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = semantic.SkepticSemanticHandoffTests()
            run, task, env, start, _ = helper.prepare(directory)
            self.assertNotIn("error", helper.query(run, task, task["allowed_evidence_ids"]))
            record, _ = helper.stop(env, start, helper.draft(task, run=run))
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            self.assertEqual(stage.finalize_skeptic_phase(semantic.fixtures.ROOT, run)["status"], "PASSED")
            package = json.loads((run / "research/skeptic/pre-decision-research-package.json").read_text())
            contract = json.loads((semantic.fixtures.ROOT / "product/schemas/runtime/pre-decision-research-package.schema.json").read_text())
            before = snapshot(run)
            moved = Path(directory) / "copied-package"
            shutil.copytree(run, moved)
            shutil.rmtree(run)
            with patch("product.runtime.invocation.verify_invocation_manifest", side_effect=AssertionError("不读取当前 Agent")):
                stage.validate_predecision_package(Path(directory) / "missing-repository", moved, package,
                                                   for_execution=False, artifact_schema=contract)
            self.assertEqual(snapshot(moved), before)
            with self.assertRaisesRegex(stage.IndependentSkepticStageError, "SCHEMA_OVERRIDE_FORBIDDEN"):
                stage.validate_predecision_package(semantic.fixtures.ROOT, moved, package,
                                                   artifact_schema=contract)


if __name__ == "__main__":
    unittest.main()
