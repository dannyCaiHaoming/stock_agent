"""目标依赖闭包与历史复用的真实校验；不启动或模拟模型。"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from product.runtime import multidimensional_stage as stage
from product.runtime.hashing import file_hash, legacy_envelope_hash
from tests import test_multidimensional_references as references


class TargetedResearchClosureTests(unittest.TestCase):

    def test_invalid_dependency_graph_is_rejected_not_silently_shrunk(self):
        source = {"task_id": "source", "task_name": "source-task", "depends_on": []}
        target = {"task_id": "target", "task_name": "target-task", "depends_on": ["source"]}
        cases = [
            ([source, {**target, "depends_on": ["missing"]}], "DEPENDENCY_UNKNOWN"),
            ([{**source, "depends_on": ["target"]}, target], "DEPENDENCY_CYCLE"),
            ([source, {**target, "depends_on": [None]}], "DEPENDENCY_INVALID"),
            ([source, {**target, "depends_on": ["source", "source"]}], "DEPENDENCY_INVALID"),
            ([source, target, {**source, "task_name": "duplicate-id"}], "INDEX_AMBIGUOUS"),
            ([source, target, {**source, "task_id": "duplicate-name"}], "INDEX_AMBIGUOUS"),
        ]
        for tasks, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(stage.MultidimensionalStageError, code):
                stage._target_task_closure({"tasks": tasks}, "target-task")
        self.assertEqual(stage._target_task_closure({"tasks": [source, target]}, "target-task"), [source, target])

    def test_current_agent_and_skill_drift_rejects_historical_reuse_read_only(self):
        for function in ("_agent_binding", "_skill_binding"):
            with self.subTest(function=function), tempfile.TemporaryDirectory() as directory:
                _, run, target = references.ReferenceBoundaryTests().prepare_with_document(Path(directory))
                before = {p: file_hash(p) for p in run.rglob('*') if p.is_file()}
                with patch.object(stage, function, return_value={"hash": "incompatible-current-resource"}), patch(
                    'subprocess.run'
                ) as process, self.assertRaisesRegex(stage.MultidimensionalStageError, 'REUSE_VERSION_INCOMPATIBLE'):
                    stage._verified_retry_dependencies(run, target['task_name'])
                process.assert_not_called()
                self.assertEqual(before, {p: file_hash(p) for p in before})

    def test_cross_run_resigned_task_index_is_not_reusable(self):
        with tempfile.TemporaryDirectory() as directory:
            _, run, target = references.ReferenceBoundaryTests().prepare_with_document(Path(directory))
            index_path = run / 'research/dispatch-index.json'
            index = json.loads(index_path.read_text())
            index['run_id'] = 'foreign-run'
            index['index_hash'] = legacy_envelope_hash(index, hash_field='index_hash')
            index_path.write_text(json.dumps(index))
            manifest_path = run / 'run_manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['dispatch_index_hash'] = index['index_hash']
            manifest['manifest_hash'] = legacy_envelope_hash(manifest, hash_field='manifest_hash')
            manifest_path.write_text(json.dumps(manifest))
            before = {p: file_hash(p) for p in run.rglob('*') if p.is_file()}
            with patch('subprocess.run') as process, self.assertRaisesRegex(
                stage.MultidimensionalStageError, 'REUSE_BINDING_INVALID'
            ):
                stage._verified_retry_dependencies(run, target['task_name'])
            process.assert_not_called()
            self.assertEqual(before, {p: file_hash(p) for p in before})
