"""当前写入/启动与冻结历史读取分离；实际 MCP 和读取器，零模型。"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime import research_submission as submission
from product.runtime import multidimensional_stage as stage
from product.runtime.fixture_mcp import StatelessFixtureTools, serve_stdio
from product.runtime.hashing import canonical_hash, file_hash
from tests import test_research_submission as fixtures
from tests import test_multidimensional_stage as stage_fixtures


class SubmissionProtocolAdmissionTests(unittest.TestCase):
    def test_missing_historical_receipt_does_not_create_submission_directory(self):
        helper = fixtures.ResearchSubmissionTests()
        with tempfile.TemporaryDirectory() as directory:
            _, run, task, _, _ = helper.submit_and_start(Path(directory), version=submission.VERSION)
            packet = submission._packet(run, task['invocation_id'])
            record = {'identity_binding': {'status': 'BOUND'}, 'trusted_task_binding': packet['identity']}
            before = {str(path.relative_to(run)): file_hash(path) for path in run.rglob('*') if path.is_file()}
            with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_PATH_INVALID'):
                submission.resolve(run, {'last_assistant_message': json.dumps({
                    'submission': 1, 'content_hash': 'missing',
                })}, record, 1)
            self.assertFalse((run / 'research/submissions').exists())
            self.assertEqual(before, {str(path.relative_to(run)): file_hash(path)
                                     for path in run.rglob('*') if path.is_file()})

    def test_retired_protocol_cannot_authorize_publish_or_acceptance(self):
        helper = fixtures.ResearchSubmissionTests()
        for version in sorted(submission.READ_VERSIONS - submission.WRITE_VERSIONS):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                _, run, task, _, _ = helper.submit_and_start(Path(directory), version=version)
                before = {str(path.relative_to(run)): file_hash(path) for path in run.rglob('*') if path.is_file()}
                with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_LEGACY_READ_ONLY'):
                    submission.require_write_protocol(task)
                # 即使调用方伪装成当前提交，冻结任务仍旧时也不能写接受记录。
                for binding_version in (version, submission.BOUNDED_REVISION_VERSION):
                    marker_record = {'submission_binding': {'version': binding_version}}
                    with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_LEGACY_READ_ONLY'):
                        submission.mark_accepted(run, marker_record, {'invocation_id': task['invocation_id']})
                self.assertEqual(before, {str(path.relative_to(run)): file_hash(path)
                                         for path in run.rglob('*') if path.is_file()})

    def test_current_protocol_cannot_downgrade_selection_schema_to_legacy_fields(self):
        helper = fixtures.ResearchSubmissionTests()
        for version in (None, "unsupported-selection-protocol"):
            with self.subTest(selection_version=version), tempfile.TemporaryDirectory() as directory:
                _, run, task = helper.prepare(Path(directory), version=submission.BOUNDED_REVISION_VERSION)
                index_path = run / 'research/dispatch-index.json'
                index = json.loads(index_path.read_text())
                target = next(t for t in index['tasks'] if t['invocation_id'] == task['invocation_id'])
                packet_path = run / task['packet_path']
                packet = json.loads(packet_path.read_text())
                packet['task']['calculation_selection_version'] = version
                target['calculation_selection_version'] = version
                target['packet_hash'] = canonical_hash(packet)
                packet_path.write_text(json.dumps(packet))
                index['index_hash'] = submission.legacy_envelope_hash(index, hash_field='index_hash')
                index_path.write_text(json.dumps(index))
                before = {str(path.relative_to(run)): file_hash(path) for path in run.rglob('*') if path.is_file()}
                tools = StatelessFixtureTools(default_run_dir=run)
                with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_SELECTION_PROTOCOL_INVALID'):
                    tools.research_report_submit(invocation_id=task['invocation_id'], draft={},
                                                 submission_token=packet['submission_access']['token'])
                delivered = stage.build_multidimensional_dispatch_packet(stage_fixtures.ROOT, run, task['task_name'])
                for serializer in (stage.serialize_multidimensional_model_context,
                                   stage.serialize_multidimensional_initial_context):
                    with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_SELECTION_PROTOCOL_INVALID'):
                        serializer(delivered)
                self.assertFalse((run / 'research/submissions').exists())
                self.assertEqual(before, {str(path.relative_to(run)): file_hash(path)
                                         for path in run.rglob('*') if path.is_file()})

    def test_every_retired_protocol_is_rejected_before_write_with_valid_bearer(self):
        helper = fixtures.ResearchSubmissionTests()
        for version in sorted(submission.READ_VERSIONS - submission.WRITE_VERSIONS):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                _, run, task, _, draft = helper.submit_and_start(Path(directory), version=version)
                tools = StatelessFixtureTools(default_run_dir=run)
                token = helper.token(run, task)
                before = {str(path.relative_to(run)): file_hash(path) for path in run.rglob('*') if path.is_file()}
                self.assertNotIn('research_report_submit', [item['name'] for item in tools.available_tools()])
                for credential in (None, 'wrong', token):
                    with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_LEGACY_READ_ONLY'):
                        tools.research_report_submit(invocation_id=task['invocation_id'], draft=draft,
                                                     submission_token=credential)
                self.assertFalse((run / 'research/submissions').exists())
                self.assertEqual(tools.events, [])
                self.assertEqual(before, {str(path.relative_to(run)): file_hash(path)
                                         for path in run.rglob('*') if path.is_file()})

    def test_retired_context_is_read_only_and_stdio_does_not_advertise_or_execute_writer(self):
        helper = fixtures.ResearchSubmissionTests()
        for version in sorted(submission.READ_VERSIONS - submission.WRITE_VERSIONS):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                _, run, task, _, draft = helper.submit_and_start(Path(directory), version=version)
                packet = stage.build_multidimensional_dispatch_packet(stage_fixtures.ROOT, run, task['task_name'])
                for serializer in (stage.serialize_multidimensional_model_context,
                                   stage.serialize_multidimensional_initial_context):
                    context = json.loads(serializer(packet))
                    contract = context['submission_contract']
                    self.assertEqual((contract['version'], contract['status'], contract['read_only']),
                                     (version, 'LEGACY_READ_ONLY', True))
                    self.assertIsNone(contract['tool'])
                    self.assertNotIn('submission_token', contract)
                    self.assertNotIn('maximum_submissions', contract)
                    self.assertNotIn(helper.token(run, task), json.dumps(context))
                requests = [
                    {'id': 1, 'method': 'tools/list'},
                    {'id': 2, 'method': 'tools/call', 'params': {'name': 'research_report_submit',
                        'arguments': {'invocation_id': task['invocation_id'], 'draft': draft,
                                      'submission_token': helper.token(run, task)}}},
                ]
                output = io.StringIO()
                with patch('sys.stdin', io.StringIO('\n'.join(json.dumps(x) for x in requests))), patch('sys.stdout', output):
                    serve_stdio(stateless=True, default_run_dir=run)
                responses = [json.loads(line) for line in output.getvalue().splitlines()]
                self.assertNotIn('research_report_submit', [x['name'] for x in responses[0]['result']['tools']])
                self.assertEqual(responses[1]['error']['message'], 'UNKNOWN_TOOL:research_report_submit')
                self.assertNotIn(helper.token(run, task), output.getvalue())
                self.assertFalse((run / 'research/submissions').exists())

    def test_retired_launch_cannot_create_process_or_invocation_state(self):
        helper = stage_fixtures.MultidimensionalStageTests()
        prepare = stage_fixtures.prepare_multidimensional_stage_run

        def structured(*args, **kwargs):
            return prepare(*args, **kwargs, structured_report_submission=True)

        for version in sorted(submission.READ_VERSIONS - submission.WRITE_VERSIONS):
            for mode in ('batch', 'initial', 'retry'):
                with self.subTest(version=version, mode=mode), tempfile.TemporaryDirectory() as directory:
                    with patch.object(stage_fixtures, 'prepare_multidimensional_stage_run', side_effect=structured), patch.object(
                        submission, 'LATEST_VERSION', version
                    ):
                        run, _ = helper.prepare(Path(directory), count=1)
                    index = json.loads((run / 'research/dispatch-index.json').read_text())
                    task = next(item for item in index['tasks'] if item['capability'] == 'RESEARCH_REPORT')
                    args = {} if mode == 'batch' else {'task_name': task['task_name'], 'initial_task': mode == 'initial'}
                    before = {str(path.relative_to(run)): file_hash(path) for path in run.rglob('*') if path.is_file()}
                    with patch('subprocess.run') as process, self.assertRaisesRegex(
                        stage.MultidimensionalStageError, 'NATIVE_HOST_EXECUTION_REQUIRED'
                    ):
                        stage.launch_multidimensional_stage(stage_fixtures.ROOT, run_dir=run, **args)
                    process.assert_not_called()
                    self.assertFalse((run / 'invocation').exists())
                    self.assertFalse((run / '.codex-runtime').exists())
                    self.assertEqual(before, {str(path.relative_to(run)): file_hash(path)
                                             for path in run.rglob('*') if path.is_file()})

    def test_historical_draft_resolution_preserves_bytes_and_still_rejects_tampering(self):
        helper = fixtures.ResearchSubmissionTests()
        for version in sorted(submission.READ_VERSIONS - submission.WRITE_VERSIONS):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as directory:
                _, run, task, _, draft = helper.submit_and_start(Path(directory), version=version)
                packet = stage.build_multidimensional_dispatch_packet(stage_fixtures.ROOT, run, task['task_name'])
                if version in submission.ASSEMBLY_VERSIONS:
                    receipt = helper.submit(StatelessFixtureTools(default_run_dir=run), task, draft)
                    message = receipt['final_message']
                else:
                    stored = {'binding': {'version': version, 'identity': packet['identity'],
                                          'packet_hash': canonical_hash(packet)}, 'draft': draft}
                    stored['content_hash'] = canonical_hash(stored)
                    path = submission._directory(run, task['invocation_id']) / '1.json'
                    path.write_text(json.dumps(stored))
                    message = json.dumps({'submission': 1, **({} if version == submission.LEGACY_VERSION
                                        else {'content_hash': stored['content_hash']})})
                path = submission._directory(run, task['invocation_id'], create=False) / '1.json'
                before = path.read_bytes()
                record = {'identity_binding': {'status': 'BOUND'}, 'trusted_task_binding': packet['identity']}
                snapshot = {str(item.relative_to(run)): file_hash(item) for item in run.rglob('*') if item.is_file()}
                with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_LEGACY_READ_ONLY'):
                    submission.resolve(run, {'last_assistant_message': message}, dict(record), 1,
                                       for_execution=True)
                restored = submission.resolve(run, {'last_assistant_message': message}, record, 1)
                result = json.loads(restored['last_assistant_message'])
                self.assertEqual(result['summary'], draft['summary'])
                self.assertEqual(result['run_id'], task['run_id'])
                self.assertEqual(result['data_gaps'], draft['data_gaps'])
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual(snapshot, {str(item.relative_to(run)): file_hash(item)
                                            for item in run.rglob('*') if item.is_file()})
                self.assertFalse(path.with_name('2.json').exists())
                value = json.loads(before)
                value['draft']['summary'] = '篡改而不改原 hash'
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_BINDING_INVALID'):
                    submission.resolve(run, {'last_assistant_message': message}, record, 1)

    def test_visible_current_tool_cannot_reactivate_retired_task_in_mixed_index(self):
        helper = stage_fixtures.MultidimensionalStageTests()
        prepare = stage_fixtures.prepare_multidimensional_stage_run

        def structured(*args, **kwargs):
            return prepare(*args, **kwargs, structured_report_submission=True)

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(stage_fixtures, 'prepare_multidimensional_stage_run', side_effect=structured):
                run, _ = helper.prepare(Path(directory), count=2)
            index_path = run / 'research/dispatch-index.json'
            index = json.loads(index_path.read_text())
            target = next(t for t in index['tasks'] if t['capability'] == 'RESEARCH_REPORT')
            packet_path = run / target['packet_path']
            packet = json.loads(packet_path.read_text())
            packet['task']['submission_version'] = submission.VERSION
            target['submission_version'] = submission.VERSION
            target['packet_hash'] = canonical_hash(packet)
            packet_path.write_text(json.dumps(packet))
            index['index_hash'] = submission.legacy_envelope_hash(index, hash_field='index_hash')
            index_path.write_text(json.dumps(index))
            manifest_path = run / 'run_manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['dispatch_index_hash'] = index['index_hash']
            manifest['manifest_hash'] = submission.legacy_envelope_hash(manifest, hash_field='manifest_hash')
            manifest_path.write_text(json.dumps(manifest))
            tools = StatelessFixtureTools(default_run_dir=run)
            self.assertIn('research_report_submit', [item['name'] for item in tools.available_tools()])
            # 读冻结 packet 不需要补造其尚未执行的基本面报告。
            with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_LEGACY_READ_ONLY'):
                tools.research_report_submit(invocation_id=target['invocation_id'], draft={},
                                             submission_token=packet['submission_access']['token'])
            self.assertFalse((run / 'research/submissions').exists())
            self.assertEqual(tools.events, [])
            current = next(t for t in index['tasks'] if t['capability'] == 'RESEARCH_REPORT'
                           and t['submission_version'] in submission.WRITE_VERSIONS)
            with self.assertRaisesRegex(ValueError, 'RESEARCH_SUBMISSION_CREDENTIAL_INVALID'):
                tools.research_report_submit(invocation_id=current['invocation_id'], draft={},
                                             submission_token='invalid')
            self.assertFalse((run / 'research/submissions').exists())
