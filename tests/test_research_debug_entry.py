"""冻结资料复用/最小闭包的确定性接缝；不调用模型、来源网络或 Gate。"""
from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from product.runtime.evidence_gate import bind_frozen_gate_to_run, validate_frozen_gate_binding
from product.runtime.hashing import file_hash, legacy_envelope_hash
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.multidimensional_stage import (
    _target_task_closure, _verified_retry_dependencies,
    build_multidimensional_task_prompt, prepare_multidimensional_stage_run, launch_multidimensional_stage,
)
from product.runtime.research_materials_stage import prepare_research_materials_stage
from tests import test_multidimensional_stage as fixtures
from tests import test_multidimensional_references as references
from tests import test_research_materials_stage as materials

ROOT = fixtures.ROOT


class ResearchDebugEntryTests(unittest.TestCase):
    def inputs(self, root):
        handoff = fixtures.stock_handoff(1)
        gate = fixtures.gate_for(handoff)
        gate['run_id'] = 'frozen-source-run'
        gate['bundle_hash'] = legacy_envelope_hash(gate, hash_field='bundle_hash')
        handoff_path, gate_path = root / 'handoff.json', root / 'gate.json'
        handoff_path.write_text(json.dumps(handoff, ensure_ascii=False))
        gate_path.write_text(json.dumps(gate, ensure_ascii=False))
        return handoff_path, gate_path, gate

    def test_source_identity_and_bytes_are_preserved_with_distinct_execution_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff, source, original = self.inputs(root)
            original_bytes = source.read_bytes()
            identities = []
            for number in range(2):
                run = root / f'run-{number}'
                identifier = f'debug-{uuid.uuid4()}'
                result = prepare_multidimensional_stage_run(
                    ROOT, handoff_path=handoff, gate_path=source, run_dir=run,
                    run_id=identifier, model='gpt-5.6-terra', reuse_frozen_gate=True,
                )
                self.assertEqual(result['status'], 'PREPARED')
                manifest = json.loads((run / 'run_manifest.json').read_text())
                gate = json.loads((run / 'evidence/gate.json').read_text())
                validate_frozen_gate_binding(run, manifest, gate)
                binding = manifest['gate_input_binding']
                self.assertEqual(binding['source_run_id'], original['run_id'])
                self.assertEqual(binding['source_file_hash'], file_hash(source))
                self.assertEqual((run / binding['source_ref']).read_bytes(), original_bytes)
                for key in original.keys() - {'run_id', 'bundle_hash', 'source_mode'}:
                    self.assertEqual(gate[key], original[key])
                tasks = json.loads((run / 'research/dispatch-index.json').read_text())['tasks']
                self.assertTrue(all(t['run_id'] == identifier and t['invocation_id'].startswith(identifier + ':')
                                    for t in tasks))
                identities.append(manifest['run_id'])
            self.assertNotEqual(*identities)
            self.assertEqual(source.read_bytes(), original_bytes)

    def test_rebinding_requires_explicit_mode_and_valid_original_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff, source, gate = self.inputs(root)
            for mode, expected in ((False, 'GATE_RUN_MISMATCH'), (True, 'SOURCE_HASH_INVALID')):
                if mode:
                    gate['decision_cutoff'] = '2025-01-01T00:00:00Z'
                    source.write_text(json.dumps(gate))
                run = root / f'rejected-{mode}'
                with self.assertRaisesRegex(ValueError, expected):
                    prepare_multidimensional_stage_run(ROOT, handoff_path=handoff, gate_path=source,
                        run_dir=run, run_id='new-debug-run', model='gpt-5.6-terra', reuse_frozen_gate=mode)
                self.assertFalse(run.exists())

    def test_counter_stage_cannot_use_gate_rebinding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            handoff, gate, _ = self.inputs(root)
            with self.assertRaisesRegex(ValueError, 'GATE_REUSE_STAGE_FORBIDDEN'):
                prepare_multidimensional_stage_run(ROOT, handoff_path=handoff, gate_path=gate,
                    run_dir=root / 'run', run_id='new-counter', model='gpt-5.6-terra',
                    stage='INDEPENDENT_COUNTER_THESIS_RESEARCH', reuse_frozen_gate=True)
            self.assertFalse((root / 'run').exists())

    def test_frozen_source_or_execution_view_tampering_is_rejected_before_launch(self):
        for defect in ('source_bytes', 'view', 'binding', 'code_drift'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                handoff, source, _ = self.inputs(root)
                run = root / 'run'
                prepare_multidimensional_stage_run(ROOT, handoff_path=handoff, gate_path=source,
                    run_dir=run, run_id='new-debug', model='gpt-5.6-terra', reuse_frozen_gate=True)
                if defect == 'source_bytes':
                    path = run / 'audit/frozen-gate-source.json'
                    path.write_bytes(path.read_bytes() + b'\n')
                else:
                    path = run / ('evidence/gate.json' if defect == 'view' else 'run_manifest.json')
                    value = json.loads(path.read_text())
                    if defect == 'code_drift':
                        value['research_execution_fingerprint']['product/runtime/fixture_mcp.py'] = '0' * 64
                        value['manifest_hash'] = legacy_envelope_hash(value, hash_field='manifest_hash')
                    elif defect == 'view':
                        value['decision_cutoff'] = '2025-01-01T00:00:00Z'
                    else:
                        value['gate_input_binding']['source_run_id'] = 'forged'
                    path.write_text(json.dumps(value))
                task = json.loads((run / 'research/dispatch-index.json').read_text())['tasks'][0]
                with patch('product.runtime.multidimensional_stage.subprocess.run') as model:
                    code = 'INITIAL_INPUT_NOT_READY' if defect == 'code_drift' else 'FROZEN_GATE_BINDING_INVALID'
                    with self.assertRaisesRegex(ValueError, code):
                        launch_multidimensional_stage(ROOT, run_dir=run, task_name=task['task_name'], initial_task=True)
                    model.assert_not_called()
                self.assertFalse((run / 'invocation').exists())

    def test_materials_prepare_shares_explicit_source_binding_without_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = materials.ResearchMaterialsStageTests().prepare(root, count=1)
            source_gate = baseline / 'evidence/gate.json'
            original = source_gate.read_bytes()
            target = root / 'new-materials'
            prepare_research_materials_stage(ROOT, handoff_path=baseline / 'audit/portfolio-handoff.json',
                gate_path=source_gate, peer_candidate_pool_path=baseline / 'research/peer-candidate-pool.json',
                run_dir=target, run_id='new-materials-run', model='gpt-5.6-terra', reuse_frozen_gate=True)
            validate_frozen_gate_binding(target, json.loads((target / 'run_manifest.json').read_text()),
                                         json.loads((target / 'evidence/gate.json').read_text()))
            self.assertEqual(source_gate.read_bytes(), original)
            self.assertFalse((target / 'invocation').exists())

    def test_options_and_report_have_only_their_minimal_dependency_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _ = fixtures.MultidimensionalStageTests().prepare(Path(directory), count=1)
            index = json.loads((run / 'research/dispatch-index.json').read_text())
            for capability, expected in (('OPTIONS_FLOW', ['OPTIONS_FLOW']),
                                         ('RESEARCH_REPORT', ['FUNDAMENTAL_EVENT', 'RESEARCH_REPORT'])):
                task = next(t for t in index['tasks'] if t['capability'] == capability)
                closure = _target_task_closure(index, task['task_name'])
                self.assertEqual([t['capability'] for t in closure], expected)
                prompt = build_multidimensional_task_prompt(ROOT, run, task['task_name'])
                for foreign in (t for t in index['tasks'] if t not in closure):
                    self.assertNotIn('"' + foreign['task_name'] + '"', prompt)

    def test_options_host_launcher_dispatches_only_one_task_and_never_claims_eight_dimensions(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = fixtures.MultidimensionalStageTests()
            run, _ = helper.prepare(Path(directory), count=1)
            index = json.loads((run / 'research/dispatch-index.json').read_text())
            target = next(t for t in index['tasks'] if t['capability'] == 'OPTIONS_FLOW')
            launched = []

            def simulated(command, *, input, cwd, env, **kwargs):
                self.assertEqual(json.loads(env['STOCK_AGENT_RESEARCH_TASK_NAMES']), [target['task_name']])
                parent, child = 'options-parent', 'options-child'
                allowed, _ = handle_hook_event(helper.dispatch_payload(target, parent=parent), environ=env)
                self.assertEqual(allowed['decision'], 'ALLOW')
                launched.append(target['task_name'])
                started, _ = handle_hook_event(helper.start_payload(target, parent=parent, child=child), environ=env)
                self.assertEqual(started['context_binding']['status'], 'DELIVERED')
                stopped, _ = handle_hook_event(helper.stop_payload(target, helper.dimension_draft(target),
                    parent=parent, child=child), environ=env)
                self.assertEqual(stopped['output_capture']['status'], 'SAVED')
                (Path(env['TMPDIR']) / 'final-message.json').write_text(json.dumps({
                    'stage': 'MULTI_DIMENSIONAL_HOLDING_RESEARCH', 'run_id': index['run_id'],
                    'dispatched': 1, 'completed': 1,
                }))
                return subprocess.CompletedProcess([], 0, '', '')

            with patch('product.runtime.multidimensional_stage.subprocess.run', side_effect=simulated):
                result, code = launch_multidimensional_stage(ROOT, run_dir=run,
                    task_name=target['task_name'], initial_task=True)
            self.assertEqual(code, 0, result)
            self.assertEqual(launched, [target['task_name']])
            self.assertFalse(result['complete_holding_research_bundle'])
            proof = json.loads((run / 'research/task-execution-proof.json').read_text())
            self.assertEqual(proof['task_names'], [target['task_name']])
            self.assertEqual(len(proof['report_inventory']), 1)
            self.assertFalse((run / 'research/holding-research-bundle.json').exists())

    def test_unknown_missing_cyclic_or_ambiguous_dependency_is_rejected(self):
        index = {'tasks': [
            {'task_id': 'a', 'task_name': 'first', 'depends_on': []},
            {'task_id': 'b', 'task_name': 'second', 'depends_on': ['a']},
        ]}
        defects = [('TARGET_TASK_UNKNOWN', index, 'unknown')]
        missing = copy.deepcopy(index)
        missing['tasks'][1]['depends_on'] = ['missing']
        defects.append(('DEPENDENCY_UNKNOWN', missing, 'second'))
        cycle = copy.deepcopy(index)
        cycle['tasks'][0]['depends_on'] = ['b']
        defects.append(('DEPENDENCY_CYCLE', cycle, 'second'))
        duplicate = copy.deepcopy(index)
        duplicate['tasks'][1]['task_name'] = 'first'
        defects.append(('INDEX_AMBIGUOUS', duplicate, 'first'))
        for code, value, name in defects:
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, code):
                _target_task_closure(value, name)

    def test_retry_dependency_configuration_drift_or_missing_lock_is_not_reusable(self):
        for defect in ('shared_code', 'missing', 'skill', 'agent', 'model', 'allowed_ids', 'cutoff'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                _, run, target = references.ReferenceBoundaryTests().prepare_with_document(Path(directory))
                self.assertEqual(len(_verified_retry_dependencies(run, target['task_name'])), 1)
                manifest_path = run / 'run_manifest.json'
                manifest = json.loads(manifest_path.read_text())
                if defect in ('shared_code', 'missing', 'skill', 'agent'):
                    if defect == 'shared_code':
                        manifest['research_execution_fingerprint']['product/runtime/fixture_mcp.py'] = '0' * 64
                    elif defect == 'missing':
                        manifest.pop('research_execution_fingerprint')
                    elif defect == 'skill':
                        manifest['skill_bindings']['company-research']['version'] = 'foreign'
                    else:
                        manifest['agent_bindings']['runtime_company_analyst']['version'] = 'foreign'
                    manifest['manifest_hash'] = legacy_envelope_hash(manifest, hash_field='manifest_hash')
                    manifest_path.write_text(json.dumps(manifest))
                elif defect == 'model':
                    path = run / target['invocation_path']
                    invocation = json.loads(path.read_text())
                    invocation['model'] = 'foreign'
                    invocation['manifest_hash'] = legacy_envelope_hash(invocation, hash_field='manifest_hash')
                    path.write_text(json.dumps(invocation))
                else:
                    path = run / 'research/dispatch-index.json'
                    index = json.loads(path.read_text())
                    task = next(t for t in index['tasks'] if t['task_name'] == target['task_name'])
                    if defect == 'allowed_ids':
                        task['allowed_evidence_ids'] = ['foreign-evidence']
                    else:
                        task['time_context']['window_end'] = '2025-01-01T00:00:00Z'
                    index['index_hash'] = legacy_envelope_hash(index, hash_field='index_hash')
                    path.write_text(json.dumps(index))
                with self.assertRaisesRegex(ValueError, 'REUSE_VERSION_INCOMPATIBLE'):
                    _verified_retry_dependencies(run, target['task_name'])


if __name__ == '__main__':
    unittest.main()
